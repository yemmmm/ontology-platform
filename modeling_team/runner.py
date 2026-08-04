"""Foreground single-run lifecycle and newline-delimited JSON outer protocol."""

from __future__ import annotations

import json
import hashlib
import os
import shutil
import threading
from copy import deepcopy
from datetime import UTC, datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


from .contracts import (
    TeamConfiguration,
    TeamConfigurationError,
    digest_file,
    load_formal_team_configuration,
)
from .acceptance import (
    AcceptanceContractError,
    CoordinatorPhaseController,
    RunnerAcceptanceCarrier,
)
from .preflight import normalize_formal_scope, run_prestart_preflight
from .runtimes.base import RuntimeAdapter, RuntimeDelivery
from .protocol_mcp_launch import (
    canonical_protocol_mcp_mode_contract,
    protocol_mcp_reasoner_contract,
)
from .protocol_mechanics import (
    build_candidate_item_evidence_map,
)
from .matrix_artifact import MatrixArtifactError, verify_matrix as verify_proof_matrix
from .start_ledger import (
    R2_3_002_REQUIREMENT_ID,
    R2_3_005_REQUIREMENT_ID,
    StartLedger,
    StartLedgerConfig,
    resolve_ledger_config,
)
from .transport_mcp import TeamTransportBroker


_PROOF_MATRIX_RELATIVE = "modeling_team/references/r2-3-002-proof-v2-assertion-matrix.json"
_P2A_PASS_RELATIVE = "workspaces/modeling-runs/.r2-3-002-proof-v2-gates/p2a-pass.json"
_MATRIX_SCHEMA = "r2-3-002-proof-v2-assertion-matrix/v1"
_P2A_SCHEMA = "r2-3-002-proof-v2-gates/p2a-pass/v1"
_OWNER_ANSWER_AUTHORIZATION = "r2-3-002-owner-answer-authorization"


@dataclass
class TeamRun:
    run_id: str
    root: Path
    configuration: TeamConfiguration
    scope: dict[str, str]
    protocol_key: str | None = None
    transport_root: Path | None = None
    baseline_hash: str | None = None
    terminal_results: dict[str, dict[str, Any]] | None = None
    protocol_context: dict[str, str] | None = None
    gate_binding: dict[str, str] | None = None
    acceptance: RunnerAcceptanceCarrier | None = None


class TeamRunner:
    def __init__(
        self,
        *,
        repository_root: Path,
        adapter: RuntimeAdapter,
        scope_factory: Any | None = None,
        ledger_root: Path | None = None,
        ledger_factory: Callable[..., StartLedger] | None = None,
        freeze_started_at: str | None = None,
        ledger_now: Callable[[], datetime] | None = None,
        prestart_preflight: Callable[..., dict[str, Any]] | None = None,
        canonical_base_url: str = "http://127.0.0.1:8001",
        canonical_admin_key: str | None = None,
    ):
        self.repository_root, self.adapter, self.scope_factory, self.ledger_root, self.ledger_factory, self.freeze_started_at, self.ledger_now = (
            repository_root,
            adapter,
            scope_factory,
            ledger_root,
            ledger_factory,
            freeze_started_at,
            ledger_now,
        )
        self.prestart_preflight = prestart_preflight
        self.canonical_base_url = canonical_base_url
        self.canonical_admin_key = canonical_admin_key
        self.run: TeamRun | None = None
        self.transport: TeamTransportBroker | None = None
        self.scope: Any | None = None
        self._terminal_emitted = False
        self._terminal_handoffs_notified: set[tuple[str, str]] = set()
        self._terminal_handoff_sequence = 0
        self._post_settlement_reporting_requested = False
        self._coordinator_final_captured = False
        self._outer_user_texts: set[str] = set()
        self._outer_questions: dict[str, dict[str, Any]] = {}
        self._owner_answers: dict[tuple[str, str], dict[str, str]] = {}
        self._owner_answer_failures: set[tuple[str, str]] = set()
        self._owner_answer_consumed: set[str] = set()
        self._owner_answer_attempts: dict[str, dict[str, str]] = {}
        self._outer_answer_sequence = 0
        self._ledger: StartLedger | None = None
        self.acceptance: RunnerAcceptanceCarrier | None = None
        self.coordinator_phase: CoordinatorPhaseController | None = None
        self._cleanup_evidence_cache: dict[str, Any] | None = None

    @staticmethod
    def _safe_run_id(value: str) -> bool:
        import re

        return bool(re.fullmatch(r"[a-z0-9][a-z0-9-]{2,80}", value))

    def _canonical_ledger_root(self) -> Path:
        return self.repository_root / "workspaces" / "modeling-runs"

    def _reject_formal_ledger_root_override(self) -> None:
        """Keep formal runs on the shared repository-owned ledger namespace."""

        if self.ledger_root is None:
            return
        supplied = Path(self.ledger_root).absolute()
        canonical = self._canonical_ledger_root().absolute()
        if supplied != canonical:
            raise TeamConfigurationError(
                "formal R2.3-005 Runner does not accept an alternate ledger_root"
            )

    def _create_ledger(
        self,
        *,
        root: Path,
        config: StartLedgerConfig,
    ) -> StartLedger:
        if self.ledger_factory is None:
            return StartLedger(root, now=self.ledger_now, config=config)
        factory = self.ledger_factory
        # The seam is intentionally explicit for deterministic temporary-ledger
        # tests.  Accept a small set of equivalent signatures so tests can keep
        # the factory independent of the production root while still receiving
        # the immutable requirement policy.
        import inspect

        try:
            signature = inspect.signature(factory)
        except (TypeError, ValueError) as exc:
            raise TeamConfigurationError("ledger factory signature is unavailable") from exc
        candidates = (
            {"root": root, "config": config, "now": self.ledger_now},
            {"ledger_root": root, "config": config, "ledger_now": self.ledger_now},
            {"root": root, "config": config},
            {"ledger_root": root, "config": config},
            {"config": config},
            {"root": root},
            {},
        )
        for kwargs in candidates:
            try:
                signature.bind(**kwargs)
            except TypeError:
                continue
            value = factory(**kwargs)
            if type(value) is not StartLedger:
                raise TeamConfigurationError("ledger factory returned an invalid ledger")
            if value.config != config:
                raise TeamConfigurationError("ledger factory configuration drifts")
            try:
                expected_path = (root / config.ledger_filename).resolve()
                expected_lock_path = (root / config.lock_filename).resolve()
                actual_path = Path(value.path).resolve()
                actual_lock_path = Path(value.lock_path).resolve()
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                raise TeamConfigurationError("ledger factory returned invalid ledger paths") from exc
            if actual_path != expected_path or actual_lock_path != expected_lock_path:
                raise TeamConfigurationError(
                    "ledger factory returned paths outside the canonical ledger root"
                )
            return value
        raise TeamConfigurationError("ledger factory signature is invalid")

    def prepare(
        self, *, run_id: str, profile_path: Path, task_path: Path, scope: dict[str, str]
    ) -> TeamRun:
        if self.run is not None or not self._safe_run_id(run_id):
            raise TeamConfigurationError("unsafe or already attached run ID")
        # R2.3-005 is the formal Runner entrypoint.  It must fail closed on a
        # legacy three-role/source-specialist Profile before a scope or Agent
        # starts.  Historical callers now migrate their fixtures to the same
        # exact four-role contract.
        config = load_formal_team_configuration(
            profile_path, task_path, root=self.repository_root
        )
        if config.task.schema_version == 2 and not self.freeze_started_at:
            raise TeamConfigurationError("v2 Task requires explicit freeze_started_at")
        formal_acceptance = (
            config.task.schema_version == 2
            and (
                config.task.task_id == "r2-3-005-formal-acceptance"
                or config.profile.profile_id == "r2-3-005-modeling-team"
            )
        )
        if formal_acceptance:
            self._reject_formal_ledger_root_override()
        normalized_scope: dict[str, str] = dict(scope)
        if formal_acceptance:
            normalized_scope = normalize_formal_scope(scope)
        root = self.repository_root / "workspaces" / "modeling-runs" / run_id
        if root.exists():
            raise TeamConfigurationError("run directory already exists")
        baseline = self._baseline_manifest(
            run_id=run_id,
            configuration=config,
            profile_path=profile_path,
            task_path=task_path,
        )
        baseline_hash = StartLedger.baseline_hash(baseline)
        preflight_evidence: dict[str, Any] | None = None
        if formal_acceptance:
            # This is deliberately before ledger reservation, run-root creation,
            # scope construction, or any Agent start.  A second baseline read
            # closes the TOCTOU gap between inventory and reservation.
            preflight_evidence = run_prestart_preflight(
                repository_root=self.repository_root,
                base_url=self.canonical_base_url,
                admin_key=self.canonical_admin_key,
                probe=self.prestart_preflight,
            )
            baseline_after_preflight = self._baseline_manifest(
                run_id=run_id,
                configuration=config,
                profile_path=profile_path,
                task_path=task_path,
            )
            if StartLedger.baseline_hash(baseline_after_preflight) != baseline_hash:
                raise TeamConfigurationError("baseline manifest drifted during preflight")
        gate_binding = None
        if formal_acceptance:
            profile_binding = config.profile.expected_matrix_binding
            task_binding = config.task.expected_matrix_binding
            if profile_binding is not None and task_binding is not None and profile_binding != task_binding:
                raise TeamConfigurationError("Profile and Task expected_matrix_binding drift")
            expected_binding = task_binding or profile_binding
            if expected_binding:
                gate_binding = self._resolve_expected_matrix_binding(expected_binding)
        if config.task.schema_version == 2:
            ledger_config = resolve_ledger_config(
                R2_3_005_REQUIREMENT_ID if formal_acceptance else R2_3_002_REQUIREMENT_ID
            )
            ledger_root = self._canonical_ledger_root()
            if not formal_acceptance and self.ledger_root is not None:
                ledger_root = self.ledger_root
            self._ledger = self._create_ledger(root=ledger_root, config=ledger_config)
            # The reservation is the freeze gate: no mutable run state exists before it succeeds.
            self._ledger.reserve(
                run_id,
                baseline_hash,
                self.freeze_started_at,
                gate_binding=gate_binding,
            )
        root.mkdir(parents=True, mode=0o700)
        (root / "evidence").mkdir(mode=0o700)
        self.run = TeamRun(run_id, root, config, normalized_scope, gate_binding=gate_binding)
        acceptance_child_factory = getattr(self.adapter, "acceptance_child_factory", None)
        source_materials: dict[str, Path] = {}
        ticket_policy: dict[str, Any] | None = None
        examiner_descriptors: dict[str, dict[str, Any]] | None = None
        if formal_acceptance:
            for source in config.task.role_sources:
                if source.classification in {"business-source", "consumer-question"}:
                    # Resolve policy digests and Source-child bytes from the
                    # immutable run-local staging copy, not a mutable checkout
                    # path after prepare.
                    source_materials[source.relative_path.as_posix()] = (
                        root / "sources" / "modeling" / source.relative_path
                    )
            ticket_policy = self._acceptance_ticket_policy(config)
            examiner_descriptors = {}
            for kind in ("source", "platform"):
                package_path = self.repository_root / "modeling_team" / "agent-packages" / f"{kind}-examiner" / "package.yaml"
                descriptor = RunnerAcceptanceCarrier.default_descriptor(kind)
                descriptor["package_digest"] = digest_file(package_path)
                examiner_descriptors[kind] = descriptor
        self.acceptance = RunnerAcceptanceCarrier(
            root / "acceptance-carrier",
            task_id=config.task.task_id,
            acceptance_id="acceptance",
            child_factory=acceptance_child_factory if callable(acceptance_child_factory) else None,
            descriptors=examiner_descriptors,
            source_materials=source_materials,
            ticket_policy=ticket_policy,
        )
        self.coordinator_phase = CoordinatorPhaseController()
        self.run.acceptance = self.acceptance
        self._atomic_json(
            root / "state.json",
            {
                "state": "PREPARING",
                "run_id": run_id,
                "profile_id": config.profile.profile_id,
                "task_id": config.task.task_id,
                "formal_roles": [agent.package.role for agent in config.profile.agents],
                "acceptance_carrier": "acceptance-carrier",
            },
        )
        shutil.copyfile(profile_path, root / "profile.snapshot.yaml")
        shutil.copyfile(task_path, root / "task.snapshot.yaml")
        self._stage_sources()
        self._record_runtime_core_hashes("before_start")
        self._atomic_json(root / "baseline-manifest.json", baseline)
        if preflight_evidence is not None:
            self._atomic_json(root / "evidence" / "prestart-preflight.json", preflight_evidence)
        self.run.baseline_hash = baseline_hash
        if config.task.schema_version == 2:
            self._append_evidence(
                "start-ledger",
                {
                    "event": "reservation",
                    "baseline_hash": self.run.baseline_hash,
                    **self._formal_ledger_identity(),
                },
            )
        return self.run

    def _acceptance_ticket_policy(self, configuration: TeamConfiguration) -> dict[str, Any]:
        """Load the requirement-owned CQ/source standard without any answers."""

        parameter = configuration.profile.parameters.get("acceptance_standard")
        if not isinstance(parameter, str) or not parameter:
            raise TeamConfigurationError("formal profile omits acceptance standard")
        standard_path = (self.repository_root / parameter).resolve()
        if self.repository_root.resolve() not in standard_path.parents:
            raise TeamConfigurationError("acceptance standard escapes repository")
        try:
            standard = json.loads(standard_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TeamConfigurationError("acceptance standard is unreadable") from exc
        if not isinstance(standard, dict):
            raise TeamConfigurationError("acceptance standard is not an object")
        questions = standard.get("competency_questions")
        if not isinstance(questions, list) or len(questions) != 2:
            raise TeamConfigurationError("acceptance standard must freeze two competency questions")
        normalized_questions: list[dict[str, str]] = []
        source_paths_by_question: dict[str, list[str]] = {}
        for item in questions:
            if not isinstance(item, dict) or set(item) != {"id", "question", "approved_source_paths"}:
                raise TeamConfigurationError("acceptance standard competency question fields drift")
            if not isinstance(item["id"], str) or not isinstance(item["question"], str) or not item["id"] or not item["question"]:
                raise TeamConfigurationError("acceptance standard competency question is invalid")
            paths = item["approved_source_paths"]
            if not isinstance(paths, list) or not paths or any(not isinstance(path, str) for path in paths):
                raise TeamConfigurationError("acceptance standard source paths are invalid")
            normalized_questions.append({"id": item["id"], "question": item["question"]})
            source_paths_by_question[item["id"]] = sorted(paths)
        if [item["id"] for item in normalized_questions] != ["cq-001", "cq-002"]:
            raise TeamConfigurationError("acceptance standard CQ ordering is invalid")
        artifact = {"path": parameter, "digest": digest_file(standard_path)}
        return {
            "quality_standard_ref": str(standard.get("requirement_ref", "")),
            "quality_standard_digest": artifact["digest"],
            "quality_standard_artifact": artifact,
            "unknown_policy": standard.get("unknown_policy"),
            "competency_questions": normalized_questions,
            "approved_source_paths_by_question": source_paths_by_question,
        }

    def _stage_sources(self) -> None:
        assert self.run
        task = self.run.configuration.task
        sources = self.run.root / "sources"
        sources.mkdir(mode=0o700)
        manifest: list[dict[str, Any]] = []
        if task.schema_version == 1:
            for source in task.allowed_sources:
                target = sources / source.name
                shutil.copyfile(source, target)
                os.chmod(target, 0o444)
                manifest.append({"path": source.name, "sha256": digest_file(source), "roles": ["all"]})
        else:
            for agent in self.run.configuration.profile.agents:
                (sources / agent.package.role).mkdir(mode=0o700, parents=True, exist_ok=True)
            for source in task.role_sources:
                for role in source.roles:
                    target = sources / role / source.relative_path
                    target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
                    shutil.copyfile(source.path, target)
                    os.chmod(target, 0o444)
                manifest.append(
                    {
                        "path": source.relative_path.as_posix(),
                        "classification": source.classification,
                        "roles": sorted(source.roles),
                        "sha256": digest_file(source.path),
                    }
                )
        self._atomic_json(self.run.root / "source-manifest.json", {"sources": manifest})

    def _baseline_manifest(
        self,
        *,
        run_id: str,
        configuration: TeamConfiguration,
        profile_path: Path,
        task_path: Path,
    ) -> dict[str, Any]:
        files = {
            "runner": self.repository_root / "modeling_team/runner.py",
            "acceptance_contract": self.repository_root / "modeling_team/acceptance.py",
            "acceptance_runtime": self.repository_root / "modeling_team/acceptance_runtime.py",
            "capability_mcp": self.repository_root / "modeling_team/capability_mcp.py",
            "read_proxy_mcp": self.repository_root / "modeling_team/read_proxy_mcp.py",
            "report_sink_mcp": self.repository_root / "modeling_team/report_sink_mcp.py",
            "preflight": self.repository_root / "modeling_team/preflight.py",
            "codex_adapter": self.repository_root / "modeling_team/runtimes/codex.py",
            "team_transport": self.repository_root / "modeling_team/transport_mcp.py",
            "platform_scope": self.repository_root / "modeling_team/platform_scope.py",
            "protocol_mcp_launch": self.repository_root / "modeling_team/protocol_mcp_launch.py",
            "protocol_mechanics": self.repository_root / "modeling_team/protocol_mechanics.py",
            "proof_v2": self.repository_root / "modeling_team/proof_v2.py",
            "proof_matrix_generator": self.repository_root / "modeling_team/matrix_artifact.py",
            "proof_matrix_retained_handoff": self.repository_root / "modeling_team/references/r2-3-002-retained-rev7-handoff.json",
            "proof_matrix_source_manifest": self.repository_root / "docs/evaluation-scenarios/ontology-modeling-team-l3/agent-input/manifest.json",
            "protocol_retrieval_mcp": self.repository_root / "modeling_team/protocol_retrieval_mcp.py",
            "protocol_retrieval_verifier": self.repository_root / "modeling_team/protocol_mechanics.py",
            "foreground_monitor": self.repository_root / "modeling_team/foreground_monitor.py",
            "foreground_cli": self.repository_root / "modeling_team/__main__.py",
            "monitor_handoff": self.repository_root / "modeling_team/monitor_handoff.py",
            "candidate_required_assertions": self.repository_root / "modeling_team/references/candidate-required-assertions-v1.json",
            "native_retrieval_proof": self.repository_root / "modeling_team/references/native-retrieval-proof-v1.json",
            "candidate_required_assertions_v2": self.repository_root / "modeling_team/references/candidate-required-assertions-v2.json",
            "native_retrieval_proof_v2": self.repository_root / "modeling_team/references/native-retrieval-proof-v2.json",
            "p2_monitor_contract": self.repository_root / "modeling_team/references/p2-monitor-contract.json",
            "p2_monitor_handoff_contract": self.repository_root / "modeling_team/references/p2-monitor-handoff-contract.json",
            "p2_protocol_driver": self.repository_root / "modeling_team/p2_protocol_driver.py",
            "p2_protocol_driver_contract": self.repository_root / "modeling_team/references/p2-protocol-driver-contract.json",
            "p2a_protocol_driver": self.repository_root / "modeling_team/p2a_protocol_driver.py",
            "p2a_protocol_driver_contract": self.repository_root / "modeling_team/references/p2a-protocol-driver-contract.json",
            "p2_monitor_adverse_order_profile": self.repository_root / "modeling_team/profiles/p2-adverse-order-smoke.yaml",
            "p2_monitor_adverse_order_task": self.repository_root / "modeling_team/tasks/p2-adverse-order-smoke.yaml",
            "protocol_reasoner_script": self.repository_root / "backend/scripts/dev_owl_reasoner.py",
            "start_ledger": self.repository_root / "modeling_team/start_ledger.py",
            "profile": profile_path,
            "task": task_path,
            "examiner_source_package": self.repository_root / "modeling_team/agent-packages/source-examiner/package.yaml",
            "examiner_source_instructions": self.repository_root / "modeling_team/agent-packages/source-examiner/instructions.md",
            "examiner_platform_package": self.repository_root / "modeling_team/agent-packages/platform-examiner/package.yaml",
            "examiner_platform_instructions": self.repository_root / "modeling_team/agent-packages/platform-examiner/instructions.md",
            "examiner_source_skill": self.repository_root / "skills/source-examiner/SKILL.md",
            "examiner_platform_skill": self.repository_root / "skills/platform-examiner/SKILL.md",
        }
        for agent in configuration.profile.agents:
            files[f"package:{agent.package.package_id}"] = self.repository_root / "modeling_team/agent-packages" / agent.package.package_id / "package.yaml"
            files[f"instructions:{agent.package.package_id}"] = agent.package.instructions_path
            for reference in agent.package.references:
                files[f"reference:{agent.package.package_id}:{reference.relative_to(self.repository_root).as_posix()}"] = reference
            for skill in agent.package.required_skills:
                files[f"skill:{agent.package.package_id}:{skill.name}"] = skill
        for source in configuration.task.allowed_sources:
            files[f"source:{source.relative_to(self.repository_root).as_posix()}"] = source
        if configuration.task.schema_version == 2:
            for source in configuration.task.role_sources:
                files[f"source:{source.path.relative_to(self.repository_root).as_posix()}"] = source.path
        platform = self.repository_root / "backend/app/mcp"
        if platform.is_dir():
            for source in sorted(platform.rglob("*.py")):
                files[f"mcp:{source.relative_to(self.repository_root).as_posix()}"] = source
        reasoner = files["protocol_reasoner_script"]
        if reasoner.is_symlink() or not reasoner.is_file():
            raise TeamConfigurationError("Protocol reasoner script is unavailable for baseline")
        if configuration.task.schema_version == 2:
            matrix = self.repository_root / _PROOF_MATRIX_RELATIVE
            p2a = self.repository_root / _P2A_PASS_RELATIVE
            # The expected binding is fixed in Task/Profile for fresh R2.3
            # runs.  Legacy cumulative tests may compute a baseline before
            # the tester-owned artifacts are installed; retain that path's
            # compatibility while binding actual artifacts whenever present.
            expected_binding = configuration.task.expected_matrix_binding or configuration.profile.expected_matrix_binding
            if expected_binding is not None and (not matrix.is_file() or not p2a.is_file()):
                raise TeamConfigurationError("proof matrix/P2a artifacts are unavailable for baseline")
            if matrix.is_file() and not matrix.is_symlink():
                files["proof_matrix_artifact"] = matrix
            if p2a.is_file() and not p2a.is_symlink():
                files["p2a_pass_artifact"] = p2a
        digests = {name: digest_file(path) for name, path in sorted(files.items())}
        return {
            "run_id": run_id,
            "files": digests,
            "call_sites": {
                "runner.prepare": digests["runner"],
                "runner.start": digests["runner"],
                "runner._baseline_manifest": digests["runner"],
                "runner.terminal_handoff_settlement_cleanup": digests["runner"],
                "codex.start_roster": digests["codex_adapter"],
                "codex.start_task": digests["codex_adapter"],
                "transport.send": digests["team_transport"],
                "transport.report": digests["team_transport"],
                "transport.mcp_response_report_observer": digests["team_transport"],
                "transport.ack_terminal_handoff": digests["team_transport"],
                "foreground_monitor.extract_adverse_order": digests["foreground_monitor"],
                "foreground_monitor.run_foreground": digests["foreground_monitor"],
                "foreground_cli.monitor_handoff": digests["foreground_cli"],
                "monitor_handoff.protocol": digests["monitor_handoff"],
                "runner.terminal_handoff_evidence": digests["runner"],
                "runner.team_transport_event_sink": digests["runner"],
                "runner.proof_v2_preflight": digests["runner"],
                "runner.proof_v2_matrix_generator": digests["proof_matrix_generator"],
                "runner.outer_answer_fsync_delivery": digests["runner"],
                "runner.acceptance_carrier": digests["runner"],
                "runner.capability_broker": digests["capability_mcp"],
                "runner.acceptance_child_runtime": digests["acceptance_runtime"],
                "runner.acceptance_read_proxy": digests["read_proxy_mcp"],
                "runner.acceptance_report_sink": digests["report_sink_mcp"],
                "runner.coordination_phase_callback": digests["runner"],
                "p2_protocol_driver.main": digests["p2_protocol_driver"],
                "p2a_protocol_driver.main": digests["p2a_protocol_driver"],
            },
            "runtime_contract": {
                "runner_capability_mcp": {
                    "server": "runner_capability",
                    "source_path": "modeling_team/capability_mcp.py",
                    "sha256": digests["capability_mcp"],
                    "roles": {
                        "coordinator": [
                            "coordinator_publish_acceptance_ticket",
                            "coordinator_get_verdict",
                        ],
                        "acceptance": [
                            "acceptance_get_ticket",
                            "acceptance_child_start",
                            "acceptance_child_get_report",
                            "acceptance_child_recycle",
                            "acceptance_get_failure_record",
                            "submit_acceptance_result",
                            "acceptance_get_verdict",
                        ],
                    },
                    "socket_mode": "0600",
                    "token_file_mode": "0400",
                },
                "examiner_children": {
                    "kinds": ["source_examiner", "platform_examiner"],
                    "source_package": {
                        "path": "modeling_team/agent-packages/source-examiner/package.yaml",
                        "sha256": digests["examiner_source_package"],
                        "instructions_sha256": digests["examiner_source_instructions"],
                        "skill_sha256": digests["examiner_source_skill"],
                        "platform_mode": "none",
                    },
                    "platform_package": {
                        "path": "modeling_team/agent-packages/platform-examiner/package.yaml",
                        "sha256": digests["examiner_platform_package"],
                        "instructions_sha256": digests["examiner_platform_instructions"],
                        "skill_sha256": digests["examiner_platform_skill"],
                        "platform_mode": "read",
                    },
                    "read_proxy": {
                        "source_path": "modeling_team/read_proxy_mcp.py",
                        "sha256": digests["read_proxy_mcp"],
                        "socket_mode": "0600",
                        "token_file_mode": "0400",
                    },
                    "report_sink": {
                        "source_path": "modeling_team/report_sink_mcp.py",
                        "sha256": digests["report_sink_mcp"],
                        "socket_mode": "0600",
                        "token_file_mode": "0400",
                    },
                    "private_runtime": {
                        "home_mode": "0700",
                        "auth_mode": "0600",
                        "env": ["CODEX_HOME", "HOME", "PATH", "TERM", "LANG", "LC_ALL"],
                        "team_transport": False,
                        "generic_spawn": False,
                    },
                },
                "protocol_mcp_mode_env": canonical_protocol_mcp_mode_contract(),
                "protocol_mcp_reasoner_env": protocol_mcp_reasoner_contract(),
                "protocol_retrieval_mcp": {
                    "server": "protocol_mechanics",
                    "command": "/usr/bin/python3",
                    "args": ["/opt/protocol-retrieval-mcp.py"],
                    "runtime_run_id_env": "PROTOCOL_RUNTIME_RUN_ID",
                    "runtime_context_path": "/opt/mechanics-contract.json",
                    "tools": [
                        "build_candidate_receipt",
                        "verify_scoped_retrieval_fallback",
                        "write_candidate_item_evidence_map",
                    ],
                },
                "proof_v2": {
                    "candidate_schema": "candidate-required-assertions/v2",
                    "candidate_item_evidence_map_path": "evidence/candidate-item-evidence-map.json",
                    "candidate_item_evidence_map_schema": "r2-3-002-candidate-item-evidence-map/v1",
                    "matrix_path": _PROOF_MATRIX_RELATIVE,
                    "p2a_pass_path": _P2A_PASS_RELATIVE,
                    "matrix_schema": _MATRIX_SCHEMA,
                    "p2a_pass_schema": _P2A_SCHEMA,
                    "runtime_asset": {
                        "source_path": "modeling_team/proof_v2.py",
                        "staged_path": "runtime-assets/protocol/proof_v2.py",
                        "mount_path": "/opt/proof_v2.py",
                        "mode": "0600",
                        "parent_mode": "0700",
                        "sha256": digests["proof_v2"],
                    },
                },
                "p2_protocol_driver": {
                    "command": "uv",
                    "argv": [
                        "run",
                        "--project",
                        "backend",
                        "python",
                        "-m",
                        "modeling_team.p2_protocol_driver",
                        "--contract",
                        "modeling_team/references/p2-protocol-driver-contract.json",
                    ],
                    "contract_file": "modeling_team/references/p2-protocol-driver-contract.json",
                    "candidate_sender_id": "p2-synthetic-modeling",
                    "protocol_agent_id": "protocol",
                    "required_terminal_stage": "protocol_report_accepted",
                },
                "p2a_protocol_driver": {
                    "command": "uv",
                    "argv": [
                        "run",
                        "--project",
                        "backend",
                        "python",
                        "-m",
                        "modeling_team.p2a_protocol_driver",
                        "--contract",
                        "modeling_team/references/p2a-protocol-driver-contract.json",
                    ],
                    "contract_file": "modeling_team/references/p2a-protocol-driver-contract.json",
                    "candidate_sender_id": "p2a-synthetic-modeling",
                    "protocol_agent_id": "protocol",
                    "required_terminal_stage": "protocol_report_accepted",
                    "semantic_start_written": False,
                },
                "p2_monitor_adverse_order": {
                    "profile_file": "modeling_team/profiles/p2-adverse-order-smoke.yaml",
                    "task_file": "modeling_team/tasks/p2-adverse-order-smoke.yaml",
                    "extractor": "modeling_team.foreground_monitor.extract_adverse_order",
                    "evidence_file": "evidence/p2-adverse-order.jsonl",
                    "required_order": [
                        "protocol_report_rejected_missing_modeling_handoff",
                        "modeling_terminal_handoff_delivered",
                        "terminal_handoff_ack_accepted",
                        "protocol_report_retry_accepted",
                        "all_four_terminal_results_completed",
                        "all_four_settled",
                    ],
                    "handoff_contract": "modeling_team/references/p2-monitor-handoff-contract.json",
                    "handoff_environment": "ONTOLOGY_P2_MONITOR_HANDOFF",
                    "handoff_phase_deadlines_seconds": {
                        "prepared": 30.0,
                        "foreground_run": 120.0,
                        "extraction_complete": 30.0,
                    },
                    "handoff_phases": [
                        "prepared",
                        "cleanup_pending",
                        "extraction_complete",
                        "extraction_failed",
                    ],
                },
            },
            "expected_matrix_binding": configuration.task.expected_matrix_binding or configuration.profile.expected_matrix_binding,
        }

    @classmethod
    def preview_baseline(
        cls, *, repository_root: Path, run_id: str, profile_path: Path, task_path: Path
    ) -> tuple[dict[str, Any], str]:
        """Compute the prepare-time binding without creating any run or ledger state."""
        if not cls._safe_run_id(run_id):
            raise TeamConfigurationError("unsafe or already attached run ID")
        configuration = load_formal_team_configuration(
            profile_path, task_path, root=repository_root
        )
        probe = object.__new__(cls)
        probe.repository_root = repository_root
        manifest = probe._baseline_manifest(
            run_id=run_id,
            configuration=configuration,
            profile_path=profile_path,
            task_path=task_path,
        )
        return manifest, StartLedger.baseline_hash(manifest)

    def _formal_coordination_enabled(self) -> bool:
        if not self.run:
            return False
        configuration = self.run.configuration
        return (
            getattr(configuration.task, "schema_version", 1) == 2
            and (
                getattr(configuration.task, "task_id", None) == "r2-3-005-formal-acceptance"
                or getattr(configuration.profile, "profile_id", None)
                == "r2-3-005-modeling-team"
            )
        )

    def _project_binding(self) -> str | None:
        """Resolve the Project identity owned by this run's coordination mode.

        Formal R2.3-005 create-mode runs receive their Project from the live
        ``PlatformScope`` after ``prepare``.  Their normalized ``TeamRun.scope``
        intentionally contains only ``{"mode": "create"}``, so falling back to
        that input would permit a caller-supplied identity to smuggle into outer
        question/answer evidence.  Historical non-formal runs retain the legacy
        ``TeamRun.scope`` binding, including schema-v2 R2.3-002 fixtures.
        """

        if self._formal_coordination_enabled():
            project_id = getattr(self.scope, "project_id", None) if self.scope is not None else None
        elif self.run is not None:
            project_id = self.run.scope.get("project_id")
        else:
            project_id = None
        return project_id if isinstance(project_id, str) and project_id else None

    def _coordination_phase_callback(
        self,
        sender_id: str,
        recipient_id: str,
        message_kind: str,
        text: str,
        generation: int,
    ) -> dict[str, Any]:
        """Validate model-visible coordination before Broker evidence is accepted."""

        if not self.coordinator_phase:
            raise TeamConfigurationError("Coordinator phase controller is unavailable")
        if message_kind == "ready_for_acceptance":
            return self.coordinator_phase.readiness(
                sender_id=sender_id,
                message_kind=message_kind,
                text=text,
                generation=generation,
            )
        if message_kind == "silent_for_acceptance":
            return self.coordinator_phase.readiness(
                sender_id=sender_id,
                message_kind=message_kind,
                text=text,
                generation=generation,
            )
        if message_kind == "acceptance_start":
            return self.coordinator_phase.start_acceptance_round(
                sender_id=sender_id,
                round_id=text,
                generation=generation,
            )
        if message_kind == "acceptance_verdict_route":
            try:
                verdict = json.loads(text)
            except (TypeError, json.JSONDecodeError) as exc:
                raise TeamConfigurationError("Acceptance verdict route is not canonical JSON") from exc
            if not isinstance(verdict, dict):
                raise TeamConfigurationError("Acceptance verdict route is not an object")
            return self.coordinator_phase.route_verdict(
                sender_id=sender_id,
                verdict=verdict,
                generation=generation,
            )
        raise TeamConfigurationError("coordination kind is not fixed by the formal Profile")

    def _terminal_report_guard(
        self, agent_id: str, already_synchronized: bool = False
    ) -> bool:
        """Compose the existing Runtime guard with the formal Coordinator terminal gate.

        The Runtime guard still owns protocol retrieval safety.  For the formal four-role
        run, Acceptance and Coordinator are additionally blocked until Acceptance has
        persisted two same-state PASS verdicts, reclaimed both child pairs, and committed
        settlement CAS/readback.  No model/SSE/``agent_end`` semantics are changed here.
        """

        adapter_guard = getattr(self.adapter, "terminal_report_blocked", None)
        if callable(adapter_guard):
            try:
                if adapter_guard(agent_id, already_synchronized):
                    return True
            except Exception:
                return True
        if self._formal_coordination_enabled() and self.run is not None:
            role_ids = {
                agent.package.role: agent.agent_id
                for agent in self.run.configuration.profile.agents
            }
            coordinator_id = role_ids.get("coordinator", "coordinator")
            if agent_id == coordinator_id:
                return self.acceptance is None or not self.acceptance.is_settled
            acceptance_id = role_ids.get("acceptance", "acceptance")
            if agent_id == acceptance_id:
                # Acceptance itself cannot terminate after merely producing a
                # verdict.  The Delivery/Runner path must first perform the
                # complete cleanup + CAS/readback settlement transition.
                return self.acceptance is None or not self.acceptance.is_settled
        return False

    def _finalize_acceptance_if_ready(self) -> None:
        """Commit explicit Acceptance settlement before Coordinator may report terminal."""

        if not self._formal_coordination_enabled() or self.acceptance is None:
            return
        if self.acceptance.is_settled or not self.acceptance.settlement_ready():
            return
        try:
            receipt = self.acceptance.settle()
        except AcceptanceContractError:
            # A state reader may have observed drift.  The carrier records the
            # invalidation and remains non-settled; Coordinator cannot pass its guard.
            return
        self._append_evidence(
            "acceptance-settlement",
            {
                "status": receipt.get("status"),
                "settlement_cas": receipt.get("settlement_cas"),
                "final_readback": receipt.get("final_readback"),
            },
        )

    def start(self) -> None:
        if not self.run:
            raise RuntimeError("Runner is not prepared")
        self._state("STARTING")
        try:
            formal_coordination = self._formal_coordination_enabled()
            if self.scope_factory:
                self.scope = self.scope_factory(self.run)
                self.scope.retain_nonempty = self.run.configuration.task.retain_nonempty
                self.scope.prepare(self.run.scope)
                if formal_coordination and self.acceptance is not None:
                    # Bind formal Acceptance read keys only after PlatformScope has
                    # authenticated and prepared the owned Project/Ontology.  The
                    # carrier then replaces its explicit offline test double with
                    # the API-backed lifecycle and host MCP forwarder.
                    self.acceptance.bind_platform_scope(
                        self.scope,
                        repository_root=self.repository_root,
                    )
                self.run.protocol_key = self.scope.protocol_key
                if self.run.configuration.task.schema_version == 2:
                    self.run.protocol_context = self.scope.read_protocol_context()
            role_agents = {
                agent.package.role: agent.agent_id for agent in self.run.configuration.profile.agents
            }
            transport_event_lock = threading.Lock()

            def transport_event_observer(event: dict[str, object]) -> None:
                with transport_event_lock:
                    self._append_team_transport_event(event)

            self.transport = TeamTransportBroker(
                self.run.root / "transport" / "broker",
                set(self.run.configuration.profile.communication),
                terminal_dependencies={
                    role_agents["protocol"]: {role_agents["modeling"]},
                    role_agents["coordinator"]: {
                        role_agents["modeling"],
                        role_agents["protocol"],
                        role_agents["acceptance"],
                    }
                },
                modeling_agent_id=role_agents["modeling"],
                coordinator_agent_id=role_agents["coordinator"],
                terminal_report_guard=self._terminal_report_guard,
                transport_event_observer=transport_event_observer,
                coordination_phase_callback=(
                    self._coordination_phase_callback if formal_coordination else None
                ),
                coordination_event_observer=(
                    self._append_coordination_transport_event if formal_coordination else None
                ),
            )
            self.transport.start(
                [agent.agent_id for agent in self.run.configuration.profile.agents]
            )
            self.run.transport_root = self.transport.root
            (self.run.root / "transport-root").write_text(
                str(self.transport.root), encoding="utf-8"
            )
            if (
                self.acceptance is not None
                and formal_coordination
            ):
                # Runner-private capability endpoints are live before any
                # Coordinator/Acceptance process is launched.
                self.acceptance.start_capability_endpoints()
            if formal_coordination and self.coordinator_phase is not None:
                self.coordinator_phase.start()
                assignment = self.coordinator_phase.assign_slice(
                    sender_id=role_agents["coordinator"],
                    objective=self.run.configuration.task.objective,
                )
                self._append_evidence("coordination-phase", assignment)
            identities = self.adapter.start_roster(
                self.run, self.run.configuration.profile.agents
            )
            roster = [identity.agent_id for identity in identities]
            if self._ledger:
                self._probe_role_visibility()
                runtime_probe = self.adapter.probe_role_visibility(self.run)
                self._append_evidence("runtime-visibility-probe", {"passed": True, "roles": runtime_probe})
                if self.run.configuration.task.schema_version == 2 and self.run.gate_binding is not None:
                    self._preflight_proof_v2_gate()
                self._ledger.mark_semantic_start(
                    self.run.run_id,
                    gate_binding=self.run.gate_binding,
                )
                self._append_evidence(
                    "semantic-start",
                    {
                        "baseline_hash": self.run.baseline_hash,
                        **self._formal_ledger_identity(),
                    },
                )
            for agent in self.run.configuration.profile.agents:
                self.adapter.start_task(
                    agent.agent_id,
                    self._task_text(agent.package.role),
                    [str(path) for path in agent.package.required_skills],
                    roster,
                )
            self._state("RUNNING", identities=[item.agent_id for item in identities])
        except Exception:
            self._state("FAILED")
            if self._ledger and (self.run.root / "evidence" / "semantic-start.jsonl").exists():
                self.record_terminal_failure("runtime/infrastructure", False)
            if self._ledger and not (self.run.root / "evidence" / "semantic-start.jsonl").exists():
                self._ledger.release_presemantic(self.run.run_id, "startup failure before business delivery")
            self.cleanup()
            raise

    def _probe_role_visibility(self) -> None:
        """Deterministically prove staged role inputs before first business delivery."""
        assert self.run
        expected: dict[str, set[Path]] = {
            agent.package.role: set() for agent in self.run.configuration.profile.agents
        }
        for source in self.run.configuration.task.role_sources:
            for role in source.roles:
                expected[role].add(source.relative_path)
        result: dict[str, Any] = {}
        for role, paths in expected.items():
            root = self.run.root / "sources" / role
            observed = {
                item.relative_to(root)
                for item in root.rglob("*")
                if item.is_file()
            } if root.exists() else set()
            if observed != paths:
                raise TeamConfigurationError(f"role visibility probe failed for {role}")
            result[role] = {
                "paths": sorted(path.as_posix() for path in observed),
                "sha256": {path.as_posix(): digest_file(root / path) for path in sorted(observed)},
            }
        self._append_evidence("role-visibility-probe", {"passed": True, "roles": result})

    def _resolve_expected_matrix_binding(self, expected: dict[str, str]) -> dict[str, str]:
        """Resolve the tester-owned P2a digest at reservation time.

        Task/Profile files freeze only immutable matrix identity and the P2a path.  The
        tester writes the P2a envelope later, so Delivery derives its canonical digest
        immediately before the reservation and passes the resulting five-field binding
        to the existing StartLedger contract.  A legacy full binding remains accepted
        for retained fixtures, but is still re-read by the pre-start gate.
        """
        if "p2a_pass_digest" in expected:
            return dict(expected)
        required = {"proof_matrix_path", "proof_matrix_digest", "p2a_pass_path", "source_run_id"}
        if not required.issubset(expected):
            raise TeamConfigurationError("expected matrix binding is incomplete")
        if expected["proof_matrix_path"] != _PROOF_MATRIX_RELATIVE or expected["p2a_pass_path"] != _P2A_PASS_RELATIVE:
            raise TeamConfigurationError("proof v2 gate path is not canonical")
        matrix_path = self._safe_gate_path(expected["proof_matrix_path"])
        p2a_path = self._safe_gate_path(expected["p2a_pass_path"])
        matrix = self._read_gate_json(matrix_path, "proof matrix")
        try:
            verify_proof_matrix(matrix, source_run_id=expected["source_run_id"])
        except MatrixArtifactError as exc:
            raise TeamConfigurationError(str(exc)) from exc
        if expected["proof_matrix_digest"] != matrix.get("matrix_digest"):
            raise TeamConfigurationError("proof matrix gate digest drifts")
        if "source_candidate_digest" in expected and expected["source_candidate_digest"] != matrix.get("source_candidate_digest"):
            raise TeamConfigurationError("proof matrix source candidate digest drifts")
        p2a = self._read_gate_json(p2a_path, "P2a pass")
        if set(p2a) != {
            "schema_version",
            "matrix_path",
            "matrix_digest",
            "source_run_id",
            "p2a_run_id",
            "verifier_complete",
            "evidence_hashes",
            "tested_at",
        }:
            raise TeamConfigurationError("P2a pass fields drift")
        if (
            p2a.get("schema_version") != _P2A_SCHEMA
            or p2a.get("matrix_path") != _PROOF_MATRIX_RELATIVE
            or p2a.get("matrix_digest") != matrix.get("matrix_digest")
            or p2a.get("source_run_id") != expected["source_run_id"]
            or p2a.get("verifier_complete") is not True
            or not isinstance(p2a.get("p2a_run_id"), str)
            or not p2a["p2a_run_id"]
            or not isinstance(p2a.get("tested_at"), str)
            or not p2a["tested_at"]
        ):
            raise TeamConfigurationError("P2a pass binding is invalid")
        evidence_hashes = p2a.get("evidence_hashes")
        if not isinstance(evidence_hashes, list) or evidence_hashes != sorted(evidence_hashes) or len(set(evidence_hashes)) != len(evidence_hashes):
            raise TeamConfigurationError("P2a evidence hashes are not sorted and unique")
        for value in evidence_hashes:
            if not isinstance(value, str) or len(value) != 64:
                raise TeamConfigurationError("P2a evidence hash is invalid")
            try:
                int(value, 16)
            except ValueError as exc:
                raise TeamConfigurationError("P2a evidence hash is invalid") from exc
        return {
            "proof_matrix_path": expected["proof_matrix_path"],
            "proof_matrix_digest": expected["proof_matrix_digest"],
            "p2a_pass_path": expected["p2a_pass_path"],
            "p2a_pass_digest": self._canonical_digest(p2a),
            "source_run_id": expected["source_run_id"],
        }

    def _preflight_proof_v2_gate(self) -> None:
        """Validate tester-owned matrix/P2a artifacts before semantic_start.

        This is intentionally a local read-only gate.  It does not inspect a
        live candidate or candidate-local map; those belong to the post-start
        Protocol gate and are not prerequisites for consuming the ledger
        reservation.
        """
        assert self.run
        expected = self.run.gate_binding
        if expected is None:
            return
        if expected.get("proof_matrix_path") != _PROOF_MATRIX_RELATIVE or expected.get("p2a_pass_path") != _P2A_PASS_RELATIVE:
            raise TeamConfigurationError("proof v2 gate path is not canonical")
        matrix_path = self._safe_gate_path(expected["proof_matrix_path"])
        p2a_path = self._safe_gate_path(expected["p2a_pass_path"])
        matrix = self._read_gate_json(matrix_path, "proof matrix")
        try:
            verify_proof_matrix(matrix, source_run_id=expected["source_run_id"])
        except MatrixArtifactError as exc:
            raise TeamConfigurationError(str(exc)) from exc
        if matrix.get("source_run_id") != expected["source_run_id"]:
            raise TeamConfigurationError("proof matrix schema/source drifts")
        if expected.get("proof_matrix_digest") != matrix.get("matrix_digest"):
            raise TeamConfigurationError("proof matrix gate digest drifts")

        p2a = self._read_gate_json(p2a_path, "P2a pass")
        if set(p2a) != {
            "schema_version",
            "matrix_path",
            "matrix_digest",
            "source_run_id",
            "p2a_run_id",
            "verifier_complete",
            "evidence_hashes",
            "tested_at",
        }:
            raise TeamConfigurationError("P2a pass fields drift")
        if (
            p2a.get("schema_version") != _P2A_SCHEMA
            or p2a.get("matrix_path") != _PROOF_MATRIX_RELATIVE
            or p2a.get("matrix_digest") != matrix.get("matrix_digest")
            or p2a.get("source_run_id") != expected["source_run_id"]
            or p2a.get("verifier_complete") is not True
            or not isinstance(p2a.get("p2a_run_id"), str)
            or not p2a["p2a_run_id"]
            or not isinstance(p2a.get("tested_at"), str)
            or not p2a["tested_at"]
        ):
            raise TeamConfigurationError("P2a pass binding is invalid")
        evidence_hashes = p2a.get("evidence_hashes")
        if not isinstance(evidence_hashes, list) or evidence_hashes != sorted(evidence_hashes) or len(set(evidence_hashes)) != len(evidence_hashes):
            raise TeamConfigurationError("P2a evidence hashes are not sorted and unique")
        for value in evidence_hashes:
            if not isinstance(value, str) or len(value) != 64:
                raise TeamConfigurationError("P2a evidence hash is invalid")
            try:
                int(value, 16)
            except ValueError as exc:
                raise TeamConfigurationError("P2a evidence hash is invalid") from exc
        p2a_digest = self._canonical_digest(p2a)
        if expected.get("p2a_pass_digest") != p2a_digest:
            raise TeamConfigurationError("P2a pass digest drifts")
        self._append_evidence(
            "proof-v2-preflight",
            {
                "matrix_path": _PROOF_MATRIX_RELATIVE,
                "matrix_digest": matrix["matrix_digest"],
                "p2a_pass_path": _P2A_PASS_RELATIVE,
                "p2a_pass_digest": p2a_digest,
                "source_run_id": expected["source_run_id"],
                "verifier_complete": True,
            },
        )

    def _safe_gate_path(self, relative: str) -> Path:
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise TeamConfigurationError("proof v2 gate path escapes repository")
        path = self.repository_root / relative
        current = self.repository_root
        for part in Path(relative).parts:
            current = current / part
            if current.is_symlink():
                raise TeamConfigurationError("proof v2 gate path cannot be a symlink")
        resolved = path.resolve()
        if resolved != self.repository_root and self.repository_root not in resolved.parents:
            raise TeamConfigurationError("proof v2 gate path escapes repository")
        if not path.is_file():
            raise TeamConfigurationError("proof v2 gate artifact is unavailable")
        return path

    @staticmethod
    def _read_gate_json(path: Path, name: str) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise TeamConfigurationError(f"{name} is not valid JSON") from exc
        if not isinstance(value, dict):
            raise TeamConfigurationError(f"{name} must contain an object")
        return value

    @staticmethod
    def _canonical_digest(value: Any) -> str:
        return hashlib.sha256(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def validate_candidate_before_submit(
        self,
        candidate: dict[str, Any],
        client_item_ids: dict[str, str] | list[dict[str, str]],
        *,
        matrix_binding: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Validate the frozen candidate and persist its map before submit/dry-run."""
        if not self.run or self.run.configuration.task.schema_version != 2:
            raise TeamConfigurationError("candidate-before-submit gate requires a v2 run")
        expected_gate = self.run.gate_binding
        if expected_gate is not None:
            if not isinstance(matrix_binding, dict) or set(matrix_binding) != {"proof_matrix_path", "proof_matrix_digest"}:
                raise TeamConfigurationError("candidate matrix_binding is missing or invalid")
            if (
                matrix_binding.get("proof_matrix_path") != expected_gate["proof_matrix_path"]
                or matrix_binding.get("proof_matrix_digest") != expected_gate["proof_matrix_digest"]
            ):
                raise TeamConfigurationError("candidate matrix_binding drifts from frozen gate")
            self._validate_candidate_matrix(candidate, expected_gate)
        candidate_value = dict(candidate)
        if "matrix_binding" in candidate_value:
            # matrix_binding is proof metadata, not a candidate envelope field.
            candidate_value.pop("matrix_binding")
        try:
            evidence_map = build_candidate_item_evidence_map(
                candidate_value,
                client_item_ids,
                run_id=self.run.run_id,
            )
        except Exception as exc:
            if isinstance(exc, TeamConfigurationError):
                raise
            raise TeamConfigurationError(str(exc)) from exc
        path = self.run.root / "evidence" / "candidate-item-evidence-map.json"
        if path.exists() or path.is_symlink():
            raise TeamConfigurationError("candidate evidence map already exists and is immutable")
        self._write_immutable_json(path, evidence_map)
        self._append_evidence(
            "candidate-item-evidence-map",
            {
                "path": "evidence/candidate-item-evidence-map.json",
                "candidate_digest": evidence_map["candidate_digest"],
                "map_digest": evidence_map["map_digest"],
                "row_count": len(evidence_map["rows"]),
            },
        )
        return evidence_map

    def _validate_candidate_matrix(
        self, candidate: dict[str, Any], expected_gate: dict[str, str]
    ) -> None:
        matrix_path = self._safe_gate_path(expected_gate["proof_matrix_path"])
        matrix = self._read_gate_json(matrix_path, "proof matrix")
        rows = matrix.get("rows")
        if not isinstance(rows, list):
            raise TeamConfigurationError("proof matrix rows are invalid")
        row_by_id = {row.get("assertion_id"): row for row in rows if isinstance(row, dict)}
        items = candidate.get("items") if isinstance(candidate, dict) else None
        if not isinstance(items, list) or {item.get("assertion_id") for item in items if isinstance(item, dict)} != set(row_by_id):
            raise TeamConfigurationError("candidate assertion IDs do not match frozen matrix")
        for item in items:
            if not isinstance(item, dict):
                raise TeamConfigurationError("candidate assertion item is invalid")
            assertion_id = item.get("assertion_id")
            row = row_by_id.get(assertion_id)
            if row is None or item.get("graph_role") != "asserted_data":
                raise TeamConfigurationError("candidate assertion scope drifts from matrix")
            for field in ("subject", "predicate", "object", "object_kind", "object_datatype", "object_language"):
                if item.get(field) != row.get(field):
                    raise TeamConfigurationError("candidate assertion drifts from frozen matrix")
            candidate_citations = item.get("evidence_citations")
            matrix_citations = row.get("approved_citations")
            if not isinstance(candidate_citations, list) or not isinstance(matrix_citations, list):
                raise TeamConfigurationError("candidate citation set is invalid")
            if sorted(candidate_citations, key=self._canonical_bytes) != sorted(matrix_citations, key=self._canonical_bytes):
                raise TeamConfigurationError("candidate citations drift from frozen matrix")

    @staticmethod
    def _canonical_bytes(value: Any) -> bytes:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @staticmethod
    def _write_immutable_json(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        try:
            encoded = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
            os.write(descriptor, encoded)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.chmod(path, 0o444)

    def record_terminal_failure(
        self,
        classification: str,
        complete_modeling_quality_result: bool,
        repair_baseline_hash: str | None = None,
    ) -> None:
        if not self.run or not self._ledger:
            return
        self._ledger.terminal_failure(
            self.run.run_id,
            classification,
            complete_modeling_quality_result,
            repair_baseline_hash,
        )
        self._append_evidence(
            "terminal-classification",
            {
                "classification": classification,
                "complete_modeling_quality_result": complete_modeling_quality_result,
                "repair_baseline_hash": repair_baseline_hash,
            },
        )

    def _task_text(self, role: str | None = None) -> str:
        assert self.run
        task = self.run.configuration.task
        if task.schema_version == 2:
            generation = (
                self.coordinator_phase.generation
                if self._formal_coordination_enabled() and self.coordinator_phase
                else None
            )
            staged_sources = sorted(
                f"/agent/home/sources/{source.relative_path.as_posix()}"
                for source in task.role_sources
                if role in source.roles
            )
            text = (
                task.objective
                + "\nBefore requesting any teammate work or reporting a terminal result, read every staged "
                + "role-private source in this canonical list:\n"
                + "\n".join(f"- {path}" for path in staged_sources)
                + "\nRead only these role-private sources. "
                + "Use Team Transport for direct messages and call report_task_result exactly once before ending. "
                + "Protocol may use only its configured ontology-platform MCP tools."
            )
            if generation is not None:
                text += (
                    f"\nCurrent coordination generation: {generation}. "
                    "Include this non-secret generation unchanged in the role's fixed "
                    "send_coordination call."
                )
            if role == "acceptance":
                return (
                    task.objective
                    + (
                        f"\nCurrent coordination generation: {generation}. "
                        if generation is not None
                        else ""
                    )
                    + "\nYou are the persistent Acceptance role. The Runner supplies an immutable ticket, "
                    "a versioned standard, and exactly two terminal Examiner reports per round. Do not "
                    "read staged source paths, call platform tools, spawn Agents, or use generic multi-agent "
                    "features. Use only the Runner-owned Acceptance capability to acknowledge the ticket, "
                    "retrieve child reports, and submit one canonical PASS/FAIL/BLOCKED verdict to Coordinator. "
                    "Keep the Acceptance session alive across rounds; never send child terminal state through "
                    "Team Transport. Bind question, acceptance_round_id, slice revision, ticket digest, typed "
                    "evidence, and complete model-state identity in every verdict. Route only "
                    "acceptance_verdict_route to coordinator with the current generation and canonical "
                    "verdict JSON as text."
                )
            if role == "protocol":
                text += (
                    "\nYou must read the enumerated modeling-batch-item-contract.json source. "
                    "Before any platform call, read /opt/mechanics-contract.json and follow its ordered "
                    "Build Session lifecycle exactly: create with initial_checkpoint omitted or null; save the "
                    "mandatory initial checkpoint before lease acquisition; after Batch/application, validation, "
                    "reasoning, and governed query, reread the Session before saving the mandatory final "
                    "checkpoint; complete using that final receipt revision and then reread the completed Session. "
                    "Use only the contract's exact receipt bindings and checkpoint fields; do not add custom fields. "
                    "When a Codex tool presents items as Array<unknown>, that file is the platform-general "
                    "nested construction contract derived from the public handler/MCP contract: use it to construct "
                    "the Batch/Item envelope, not as a conflict or missing input. Modeling sends a platform-neutral "
                    "semantic candidate; Protocol alone translates it into the envelope and must not require Modeling "
                    "to author exact items. The public tool remains the final execution and validation authority."
                    " Reply to every Modeling candidate or revision with reply_to_delivery_id set to that candidate's "
                    "delivery_id and send a mechanical receipt or conflict. Remain active for revisions, and report "
                    "terminal only after the Runner delivers Modeling's terminal-handoff. Preserve every candidate "
                    "evidence_citations field byte-for-byte; do not read/guess source locators or owner answers. "
                    "Before the first submit_modeling_batch call, validate assertion IDs/scope/citations and the "
                    "frozen matrix binding, write the run-local candidate-item-evidence-map, and compare the "
                    "group-projected safe dry-run Evidence plan before apply. Emit only "
                    "silent_for_acceptance to coordinator through send_coordination with the current "
                    "generation after the ordered protocol work is quiet."
                )
                context = self.run.protocol_context
                if context:
                    return text + "\nMechanical platform scope (no credential): " + json.dumps(
                        context, ensure_ascii=False, sort_keys=True
                    )
            if role == "coordinator":
                return text + (
                    "\nCoordinator receives no raw business or consumer-source bytes. Use only the "
                    "Runner-private capability MCP to publish the fixed requirement-owned ticket and "
                    "read the Acceptance verdict; do not redefine CQs, approved-source paths, or the "
                    "quality standard. After Modeling-ready and Protocol-silent, emit only "
                    "acceptance_start to acceptance through send_coordination with the current "
                    "generation and acceptance_round_id as text."
                    "\nWhen forwarding an outer answer to a grounded Modeling question, send that exact answer "
                    "once with reply_to_delivery_id set to the current Modeling question delivery_id. Do not "
                    "duplicate it or leave it unbound."
                    "\nreport_task_result is recorded exactly once only after Modeling, Protocol, and Acceptance "
                    "have each reported completed or blocked. A dependency rejection is not recorded; wait for "
                    "their terminal handoffs and retry without reviewing their semantics. Coordinator reports last."
                )
            if role == "modeling":
                return text + (
                    "\nEmit only ready_for_acceptance to coordinator through send_coordination with "
                    "the current generation once the semantic slice is ready; never emit "
                    "silent_for_acceptance or acceptance_start."
                    "\nSend each platform-neutral candidate or revision with expects_reply=true and retain the "
                    "returned delivery_id. Wait for Protocol's delivered receipt or conflict whose "
                    "reply_to_delivery_id matches it. On conflict, send a revision as a new expects_reply request; "
                    "if you cannot revise, send no further candidate and report blocked. Without an established "
                    "reply request, Modeling may report only blocked, never completed. Every candidate item must "
                    "carry non-empty evidence_citations with the exact document_name, excerpt, source artifact/"
                    "locator/hash, and owner_answer_id fields; do not put platform IDs, Batch IDs, receipt labels, "
                    "or matrix answers into the platform-neutral candidate."
                )
            return text
        return (
            self.run.configuration.task.objective
            + "\nAllowed sources: "
            + ", ".join(
                f"/agent/home/sources/{path.name}"
                for path in self.run.configuration.task.allowed_sources
            )
            + "\nUse Team Transport for direct messages and call report_task_result exactly once before ending. Protocol must call check_platform_health once; do not call another platform tool."
        )

    def receive_outer(self, message: dict[str, Any]) -> list[dict[str, Any]]:
        if not self.run:
            raise RuntimeError("Runner is not prepared")
        if not isinstance(message, dict):
            raise TeamConfigurationError("outer message must be a JSON object")
        action = message.get("action")
        if action == "question":
            if self._formal_coordination_enabled():
                raise TeamConfigurationError("schema-v2 outer questions are Runner-owned")
            self._record_outer_question(message)
        elif action == "user":
            if self._formal_coordination_enabled() and set(message) != {"action", "text"}:
                raise TeamConfigurationError("schema-v2 owner answer envelope has invalid fields")
            text = message.get("text")
            if not isinstance(text, str):
                raise TeamConfigurationError("outer user text must be a string")
            coordinator = next(
                agent.agent_id
                for agent in self.run.configuration.profile.agents
                if agent.package.role == "coordinator"
            )
            if self.run.configuration.task.schema_version == 2:
                question_delivery_id: object
                if self._formal_coordination_enabled():
                    question_delivery_id = self._resolve_formal_owner_question(text)
                else:
                    question_delivery_id = message.get("question_delivery_id")
                self._release_owner_answer(
                    coordinator,
                    text,
                    question_delivery_id,
                )
            else:
                self.adapter.send_message(
                    coordinator,
                    RuntimeDelivery(
                        sender_id="user/outer",
                        recipient_id=coordinator,
                        kind="outer-user",
                        text=text,
                    ),
                )
                self._outer_user_texts.add(text)
                self._append_evidence("outer-user", {"text": text})
        elif action == "status":
            pass
        elif action == "pause":
            self.adapter.pause()
            self._state("PAUSED")
        elif action == "resume":
            self.adapter.resume()
            self._state("RUNNING")
        elif action == "stop":
            self.cleanup()
            return [{"type": "stopped"}]
        else:
            raise TeamConfigurationError("unknown outer Runner action")
        return self.drain()

    def _observe_modeling_question(self, delivery: Any) -> None:
        """Register only a formal Modeling->Coordinator reply request internally."""
        if not self._formal_coordination_enabled() or not self.run or not self.transport:
            return
        modeling = next(
            agent.agent_id
            for agent in self.run.configuration.profile.agents
            if agent.package.role == "modeling"
        )
        coordinator = next(
            agent.agent_id
            for agent in self.run.configuration.profile.agents
            if agent.package.role == "coordinator"
        )
        if (
            delivery.sender_id != modeling
            or delivery.recipient_id != coordinator
            or not delivery.expects_reply
            or delivery.reply_to_delivery_id is not None
            or not isinstance(delivery.text, str)
            or not delivery.text
        ):
            return
        delivery_id = delivery.delivery_id
        project_id = self._project_binding()
        if not isinstance(project_id, str) or not project_id:
            raise TeamConfigurationError("outer question project binding is missing")
        existing = self._outer_questions.get(delivery_id)
        if existing is not None:
            if (
                existing.get("text") != delivery.text
                or existing.get("run_id") != self.run.run_id
                or existing.get("project_id") != project_id
            ):
                raise TeamConfigurationError("outer question delivery is immutable")
            return
        self._outer_questions[delivery_id] = {
            "question_delivery_id": delivery_id,
            "project_id": project_id,
            "run_id": self.run.run_id,
            "text": delivery.text,
            "origin_agent_id": modeling,
            "displayed": False,
            "consumed": False,
        }

    def _observe_coordinator_message(self, message: Any) -> None:
        """Mark one observed candidate displayed only when Coordinator carries its exact text."""
        if not self._formal_coordination_enabled() or not self.run:
            return
        text = getattr(message, "text", None)
        if not isinstance(text, str):
            return
        candidates = [
            record
            for record in self._outer_questions.values()
            if record.get("displayed") is False and record.get("consumed") is False
        ]
        matches = [record for record in candidates if record.get("text") and record["text"] in text]
        if len(matches) > 1:
            raise TeamConfigurationError("multiple outer questions match Coordinator prompt")
        if not matches:
            return
        record = matches[0]
        record["displayed"] = True
        record["coordinator_prompt"] = text
        self._append_evidence(
            "outer-question",
            {
                key: record[key]
                for key in ("question_delivery_id", "project_id", "run_id", "text")
            },
        )

    def _resolve_formal_owner_question(self, text: str) -> str:
        """Resolve a text-only schema-v2 answer to exactly one displayed question."""
        del text  # The answer text is intentionally not part of question ownership.
        unresolved = [
            record
            for record in self._outer_questions.values()
            if record.get("consumed") is not True
        ]
        eligible = [record for record in unresolved if record.get("displayed") is True]
        if len(eligible) == 0:
            if unresolved:
                raise TeamConfigurationError("owner answer question has not been displayed")
            raise TeamConfigurationError("owner answer has no unanswered displayed question")
        if len(eligible) > 1:
            raise TeamConfigurationError("owner answer matches multiple unanswered questions")
        question = eligible[0]
        if question.get("run_id") != self.run.run_id:
            raise TeamConfigurationError("owner answer run binding drifts")
        if question.get("project_id") != self._project_binding():
            raise TeamConfigurationError("owner answer project binding drifts")
        modeling = next(
            agent.agent_id
            for agent in self.run.configuration.profile.agents
            if agent.package.role == "modeling"
        )
        if question.get("origin_agent_id") != modeling:
            raise TeamConfigurationError("owner answer question origin drifts")
        return question["question_delivery_id"]

    def _record_outer_question(self, message: dict[str, Any]) -> None:
        assert self.run
        delivery_id = message.get("delivery_id", message.get("question_delivery_id"))
        text = message.get("text")
        if not isinstance(delivery_id, str) or not delivery_id or not isinstance(text, str) or not text:
            raise TeamConfigurationError("outer question delivery is invalid")
        existing = self._outer_questions.get(delivery_id)
        if existing is not None:
            if existing["text"] != text:
                raise TeamConfigurationError("outer question delivery is immutable")
            return
        project_id = self._project_binding()
        if not isinstance(project_id, str) or not project_id:
            raise TeamConfigurationError("outer question project binding is missing")
        record: dict[str, Any] = {
            "question_delivery_id": delivery_id,
            "project_id": project_id,
            "run_id": self.run.run_id,
            "text": text,
        }
        self._outer_questions[delivery_id] = record
        self._append_evidence("outer-question", record)

    def _release_owner_answer(
        self,
        coordinator: str,
        text: str,
        question_delivery_id: object,
    ) -> None:
        assert self.run
        if not isinstance(question_delivery_id, str) or not question_delivery_id:
            raise TeamConfigurationError("owner answer requires a question delivery ID")
        question = self._outer_questions.get(question_delivery_id)
        if question is None:
            raise TeamConfigurationError("owner answer question delivery is unknown")
        formal = self._formal_coordination_enabled()
        if question.get("project_id") != self._project_binding():
            raise TeamConfigurationError("owner answer project binding drifts")
        if formal:
            if question.get("run_id") != self.run.run_id:
                raise TeamConfigurationError("owner answer run binding drifts")
            if question.get("displayed") is not True:
                raise TeamConfigurationError("owner answer question has not been displayed")
            modeling = next(
                agent.agent_id
                for agent in self.run.configuration.profile.agents
                if agent.package.role == "modeling"
            )
            if question.get("origin_agent_id") != modeling:
                raise TeamConfigurationError("owner answer question origin drifts")
        key = (question_delivery_id, text)
        existing = self._owner_answers.get(key)
        if key in self._owner_answer_failures:
            raise TeamConfigurationError("owner answer delivery previously failed and cannot be reused")
        if question.get("consumed") is True or question_delivery_id in self._owner_answer_consumed:
            # Historical non-formal fixtures called this private helper directly and
            # relied on same-key idempotence; the formal schema-v2 envelope is strict
            # and rejects every replay, including identical text.
            if existing is not None and not formal:
                return
            raise TeamConfigurationError("owner answer question delivery was already consumed")
        if existing is not None:
            return
        project_id = self._project_binding()
        if not isinstance(project_id, str) or not project_id:
            raise TeamConfigurationError("owner answer project binding is missing")
        authorization_id = self.run.configuration.profile.parameters.get(
            "owner_answer_authorization_id", _OWNER_ANSWER_AUTHORIZATION
        )
        if not isinstance(authorization_id, str) or not authorization_id:
            raise TeamConfigurationError("owner answer authorization binding is missing")
        owner_payload = {
            "run_id": self.run.run_id,
            "project_id": project_id,
            "question_delivery_id": question_delivery_id,
            "text": text,
        }
        owner_answer_id = "owner-answer-" + self._canonical_digest(owner_payload)
        self._outer_answer_sequence += 1
        release_id = f"owner-answer-delivery-{self._outer_answer_sequence}"
        record = {
            "owner_answer_id": owner_answer_id,
            "project_id": project_id,
            "run_id": self.run.run_id,
            "authorization_id": authorization_id,
            "release_id": release_id,
            "question_delivery_id": question_delivery_id,
            "delivery_id": release_id,
            "text": text,
            "released_at": datetime.now(UTC).isoformat(),
        }
        # The question is consumed before any persistence or send attempt.  This lock is
        # intentionally independent of answer text: persistence/send failures burn this
        # question and its generated identifiers rather than permitting a retry.
        question["consumed"] = True
        self._owner_answer_consumed.add(question_delivery_id)
        self._owner_answer_attempts[question_delivery_id] = record
        # The exact nine-field record is persisted and fsynced before the Broker queues
        # the direct Modeling answer.  A failed persistence/publication burns the IDs.
        try:
            self._append_exact_outer_user(record)
            if self.transport is not None and formal:
                self.transport.publish_owner_answer(
                    question_delivery_id=question_delivery_id,
                    owner_answer_id=owner_answer_id,
                    release_id=release_id,
                    text=text,
                )
            else:
                # Compatibility for the historical direct helper used by schema-v2 unit
                # fixtures that do not attach a Broker.  Formal started runs always use
                # the narrowed Broker publication above.
                self.adapter.send_message(
                    coordinator,
                    RuntimeDelivery(
                        sender_id="user/outer",
                        recipient_id=coordinator,
                        kind="outer-user",
                        text=text,
                        delivery_id=release_id,
                        reply_to_delivery_id=question_delivery_id,
                    ),
                )
        except Exception:
            self._owner_answer_failures.add(key)
            self._state("FAILED", owner_answer_id=owner_answer_id, release_id=release_id)
            self._append_evidence(
                "owner-answer-failure",
                {"owner_answer_id": owner_answer_id, "release_id": release_id},
            )
            raise
        self._owner_answers[key] = record
        self._outer_user_texts.add(text)

    def _append_exact_outer_user(self, record: dict[str, str]) -> None:
        assert self.run
        fields = {
            "owner_answer_id",
            "project_id",
            "run_id",
            "authorization_id",
            "release_id",
            "question_delivery_id",
            "delivery_id",
            "text",
            "released_at",
        }
        if set(record) != fields:
            raise TeamConfigurationError("outer-user owner answer fields drift")
        path = self.run.root / "evidence" / "outer-user.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        encoded = (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        try:
            os.write(descriptor, encoded)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _mark_owner_answer_failure(self, delivery: Any, reason: str) -> None:
        question_delivery_id = delivery.reply_to_delivery_id
        record = self._owner_answer_attempts.get(question_delivery_id)
        if record is None:
            return
        key = (question_delivery_id, record["text"])
        self._owner_answer_failures.add(key)
        self._state(
            "FAILED",
            owner_answer_id=record["owner_answer_id"],
            release_id=record["release_id"],
        )
        self._append_evidence(
            "owner-answer-failure",
            {
                "owner_answer_id": record["owner_answer_id"],
                "release_id": record["release_id"],
                "reason": reason,
            },
        )

    def drain(self) -> list[dict[str, Any]]:
        if not self.run or not self.transport:
            return []
        output: list[dict[str, Any]] = []
        coordinator = next(
            agent.agent_id
            for agent in self.run.configuration.profile.agents
            if agent.package.role == "coordinator"
        )
        for delivery in self.transport.drain():
            owner_answer = delivery.owner_answer_id is not None
            if delivery.recipient_id in self.transport.results:
                self._append_evidence(
                    "terminal-delivery-blocked",
                    {
                        "sender_id": delivery.sender_id,
                        "recipient_id": delivery.recipient_id,
                        "reason": "recipient already reported terminal result",
                    },
                )
                if owner_answer:
                    self._mark_owner_answer_failure(delivery, "recipient already reported terminal result")
                continue
            if owner_answer:
                runtime_delivery = RuntimeDelivery(
                    sender_id=delivery.sender_id,
                    recipient_id=delivery.recipient_id,
                    kind="owner-answer",
                    text=delivery.text,
                    delivery_id=delivery.delivery_id,
                    expects_reply=delivery.expects_reply,
                    reply_to_delivery_id=delivery.reply_to_delivery_id,
                    owner_answer_id=delivery.owner_answer_id,
                    release_id=delivery.release_id,
                )
            else:
                runtime_delivery = RuntimeDelivery(
                    sender_id=delivery.sender_id,
                    recipient_id=delivery.recipient_id,
                    kind=(
                        "outer-forward"
                        if delivery.sender_id == coordinator
                        and delivery.text in self._outer_user_texts
                        else "peer"
                    ),
                    text=delivery.text,
                    delivery_id=delivery.delivery_id,
                    expects_reply=delivery.expects_reply,
                    reply_to_delivery_id=delivery.reply_to_delivery_id,
                )
            try:
                self.adapter.send_message(delivery.recipient_id, runtime_delivery)
            except Exception:
                if owner_answer:
                    self._mark_owner_answer_failure(delivery, "Runtime Adapter delivery failed")
                raise
            self.transport.ack_delivery(delivery.delivery_id)
            envelope = {
                "type": "delivery",
                "sequence": delivery.sequence,
                "sender_id": delivery.sender_id,
                "recipient_id": delivery.recipient_id,
                "text": delivery.text,
                "timestamp": delivery.timestamp,
                "delivery_id": delivery.delivery_id,
                "expects_reply": delivery.expects_reply,
                "reply_to_delivery_id": delivery.reply_to_delivery_id,
            }
            if owner_answer:
                envelope.update(
                    {
                        "owner_answer_id": delivery.owner_answer_id,
                        "release_id": delivery.release_id,
                    }
                )
            output.append(envelope)
            self._append_evidence("deliveries", envelope)
            self._observe_modeling_question(delivery)
        results = self.transport.results
        self._finalize_acceptance_if_ready()
        for source_id, result in results.items():
            for recipient_id, dependencies in self.transport.terminal_dependencies.items():
                pair = (recipient_id, source_id)
                if source_id not in dependencies or pair in self._terminal_handoffs_notified:
                    continue
                # A Protocol report can be rejected before its dependency handoff arrives.  The
                # rejection is not a terminal result and must not be fabricated or counted as a
                # second report.  Include one deterministic redrive instruction in the real
                # handoff so the Protocol can retry its own report exactly once after the Broker
                # dependency is satisfied.  The immutable source result remains nested unchanged.
                recipient_role = next(
                    (
                        agent.package.role
                        for agent in self.run.configuration.profile.agents
                        if agent.agent_id == recipient_id
                    ),
                    recipient_id,
                )
                remaining_dependencies = sorted(
                    dependency
                    for dependency in dependencies
                    if dependency not in self.transport.results
                )
                if recipient_role == "protocol":
                    next_action = "retry_report_task_result_once"
                    instruction = (
                        "The Broker has now delivered the required terminal handoff. If your "
                        "earlier report_task_result was rejected for a missing dependency, call "
                        "report_task_result exactly once now; preserve Protocol ownership and "
                        "do not fabricate any other Agent result."
                    )
                elif remaining_dependencies:
                    next_action = "await_remaining_terminal_handoffs"
                    instruction = (
                        "This dependency handoff is recorded. Await every remaining terminal "
                        "handoff before calling report_task_result; do not retry or fabricate a "
                        "Coordinator result yet."
                    )
                else:
                    next_action = "retry_report_task_result_once"
                    instruction = (
                        "The Broker has now delivered all required terminal handoffs. If your "
                        "earlier report_task_result was rejected for a missing dependency, call "
                        "report_task_result exactly once now and preserve every dependency "
                        "summary."
                    )
                handoff = {
                    **result.__dict__,
                    "terminal_result": result.__dict__,
                    "next_action": next_action,
                    "instruction": instruction,
                }
                text = json.dumps(handoff, ensure_ascii=False, sort_keys=True)
                self.adapter.send_message(
                    recipient_id,
                    RuntimeDelivery(
                        sender_id="runner/terminal-result",
                        recipient_id=recipient_id,
                        kind="terminal-handoff",
                        text=text,
                    ),
                )
                self._terminal_handoff_sequence += 1
                handoff_id = f"terminal-handoff-{self._terminal_handoff_sequence}"
                delivered = {
                    "type": "terminal-result-handoff",
                    "recipient_id": recipient_id,
                    "source_id": source_id,
                    "handoff_id": handoff_id,
                    "sequence": self._terminal_handoff_sequence * 2 - 1,
                    "result": result.__dict__,
                }
                self._append_evidence("terminal-result-handoff", delivered)
                self.transport.ack_terminal_handoff(recipient_id, source_id)
                self._append_evidence(
                    "terminal-handoff-ack",
                    {
                        "agent": recipient_id,
                        "tool": "ack_terminal_handoff",
                        "status": "accepted",
                        "source_id": source_id,
                        "ack": True,
                        "handoff_id": handoff_id,
                        "sequence": self._terminal_handoff_sequence * 2,
                    },
                )
                output.append(delivered)
                self._terminal_handoffs_notified.add(pair)
        for message in self.adapter.receive_messages():
            if message.agent_id == coordinator:
                self._observe_coordinator_message(message)
                if self._post_settlement_reporting_requested:
                    self._capture_coordinator_final(message, output)
                    continue
                envelope = {"type": "coordinator", "text": message.text}
                output.append(envelope)
                self._append_evidence("coordinator", envelope)
        formal_settlement_ready = (
            not self._formal_coordination_enabled()
            or (self.acceptance is not None and self.acceptance.is_settled)
        )
        if formal_settlement_ready and not self._terminal_emitted and len(self.transport.results) == len(
            self.run.configuration.profile.agents
        ) and self.adapter.wait_settled(
            [agent.agent_id for agent in self.run.configuration.profile.agents], 1
        ):
            self._terminal_emitted = True
            self.run.terminal_results = {
                key: value.__dict__ for key, value in self.transport.results.items()
            }
            envelope = {
                "type": "settled",
                "results": {
                    key: value.__dict__ for key, value in self.transport.results.items()
                },
            }
            output.append(envelope)
            self._append_evidence("settled", envelope)
            self._state("POST_SETTLEMENT_REPORTING")
            self._post_settlement_reporting_requested = True
            self.adapter.send_message(
                coordinator,
                RuntimeDelivery(
                    sender_id="runner/post-settlement",
                    recipient_id=coordinator,
                    kind="post-settlement",
                    text=self._post_settlement_prompt(envelope["results"]),
                ),
            )
        return output

    def send_coordination(
        self,
        *,
        sender_id: str,
        recipient_id: str,
        message_kind: str,
        text: str = "",
        generation: int,
    ) -> dict[str, Any]:
        """Publish a non-terminal readiness/silence phase event.

        This is intentionally separate from ``report_task_result``.  It allows
        Coordinator to serialize Modeling/Protocol quiet acknowledgements while
        preserving the existing Agent settlement semantics.
        """
        if not self.run or not self.transport or not self.coordinator_phase:
            raise RuntimeError("Runner is not started")
        if not self._formal_coordination_enabled():
            raise TeamConfigurationError("coordination phase is unavailable for this run")
        delivery = self.transport.send_coordination(
            sender_id,
            recipient_id,
            message_kind,
            text,
            generation,
        )
        envelope = {
            "type": "coordination",
            "sender_id": delivery.sender_id,
            "recipient_id": delivery.recipient_id,
            "message_kind": delivery.message_kind,
            "message_id": delivery.message_id,
            "timestamp": delivery.timestamp,
            "terminal": False,
            "settles": False,
            "text_sha256": hashlib.sha256(delivery.text.encode("utf-8")).hexdigest(),
            "phase_event": {
                key: value
                for key, value in (delivery.phase_event or {}).items()
                if key not in {"text", "objective"}
            },
        }
        self._append_evidence("coordination", envelope)
        return envelope

    @staticmethod
    def _post_settlement_prompt(results: dict[str, Any]) -> str:
        return (
            "Runtime settlement is complete. Generate exactly one non-empty user-facing final "
            "summary from this immutable structured terminal-result snapshot. Preserve every "
            "Agent status and summary faithfully; do not call tools, send peer messages, or call "
            "report_task_result again.\nTerminal-result snapshot:\n"
            + json.dumps(results, ensure_ascii=False, sort_keys=True)
        )

    def _capture_coordinator_final(
        self, message: Any, output: list[dict[str, Any]]
    ) -> None:
        if self._coordinator_final_captured or not isinstance(message.text, str):
            return
        text = message.text.strip()
        if not text:
            return
        self._coordinator_final_captured = True
        envelope = {"type": "coordinator", "text": text}
        output.append(envelope)
        self._append_evidence("coordinator-final", envelope)
        self._state("TERMINAL_REPORT_COMPLETE")

    def cleanup(self) -> dict[str, Any]:
        if self._cleanup_evidence_cache is not None:
            return deepcopy(self._cleanup_evidence_cache)
        evidence: dict[str, Any] = {}
        self._state("CLEANING") if self.run else None
        formal = self._formal_coordination_enabled()
        acceptance_settled = bool(self.acceptance and self.acceptance.is_settled)
        if formal and not acceptance_settled:
            self._state("ABORTING") if self.run else None
        try:
            self.adapter.stop()
            evidence["runtime"] = self.adapter.cleanup_identifiers()
            if self.acceptance:
                if formal and not acceptance_settled:
                    evidence["acceptance"] = self.acceptance.abort_cleanup(
                        "runner-abort-before-settlement"
                    )
                    self._append_evidence(
                        "aborted",
                        {
                            "status": "aborted",
                            "reason": evidence["acceptance"].get("aborted_reason"),
                            "settled": False,
                        },
                    )
                else:
                    evidence["acceptance"] = self.acceptance.cleanup()
        finally:
            if self.scope:
                if self.run and self.run.terminal_results:
                    self.scope.terminal_results = self.run.terminal_results
                evidence["scope"] = self.scope.cleanup()
                if self.run and evidence["scope"].get("scope_disposition") == "retained-pending-acceptance":
                    self._write_retained_handoff_evidence(evidence["scope"])
            if self.transport:
                self.transport.stop()
            if self.run:
                if self._ledger and not (self.run.root / "evidence" / "semantic-start.jsonl").exists():
                    try:
                        self._ledger.release_presemantic(
                            self.run.run_id, "Runner cleanup before semantic start"
                        )
                        self._append_evidence(
                            "start-ledger",
                            {
                                "event": "presemantic_release",
                                **self._formal_ledger_identity(),
                            },
                        )
                    except TeamConfigurationError:
                        # Startup failure may already have recorded the same immutable correction.
                        pass
                secrets = self.run.root / "secrets"
                if secrets.exists():
                    shutil.rmtree(secrets)
                    evidence["secrets_destroyed"] = True
                self._record_runtime_core_hashes("after_cleanup")
                self._state(
                    "CLEANED",
                    cleanup=evidence,
                    terminal_results=self.run.terminal_results,
                )
        if self.run is None:
            return evidence
        self._cleanup_evidence_cache = deepcopy(evidence)
        return deepcopy(self._cleanup_evidence_cache)

    def _record_runtime_core_hashes(self, phase: str) -> None:
        self._append_evidence(
            "runtime-core-hashes",
            {
                "phase": phase,
                "runner_sha256": digest_file(self.repository_root / "modeling_team/runner.py"),
                "codex_adapter_sha256": digest_file(
                    self.repository_root / "modeling_team/runtimes/codex.py"
                ),
                "capability_mcp_sha256": digest_file(
                    self.repository_root / "modeling_team/capability_mcp.py"
                ),
                "transport_mcp_sha256": digest_file(
                    self.repository_root / "modeling_team/transport_mcp.py"
                ),
            },
        )

    def _state(self, value: str, **extra: Any) -> None:
        if self.run:
            self._atomic_json(
                self.run.root / "state.json",
                {"state": value, "run_id": self.run.run_id, **extra},
            )

    def _write_retained_handoff_evidence(self, scope: dict[str, Any]) -> None:
        """Freeze the non-semantic offline-handoff inputs exactly once after cleanup."""
        assert self.run
        required = ("project_id", "ontology_id", "workspace_version", "completed_session_id")
        if scope.get("owned") is not True or scope.get("scope_disposition") != "retained-pending-acceptance":
            raise TeamConfigurationError("retained scope evidence is not a successful owned producer")
        if (
            scope.get("mode") != "create"
            or scope.get("sessions_terminal") is not True
            or scope.get("protocol_key_revoked") is not True
            or scope.get("admin_key_revoked") is not True
        ):
            raise TeamConfigurationError("retained scope cleanup safety gate is incomplete")
        if any(not isinstance(scope.get(field), str) or not scope[field] for field in required):
            raise TeamConfigurationError("retained scope evidence is incomplete")
        results = self._completed_terminal_statuses(self.run.terminal_results)
        payload = {
            "run_id": self.run.run_id,
            "terminal_statuses": results,
            "scope": {field: scope[field] for field in (*required, "scope_disposition", "owned")},
        }
        path = self.run.root / "evidence" / "retained-handoff-input.json"
        encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode()
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        except FileExistsError as exc:
            raise TeamConfigurationError("retained handoff evidence is immutable") from exc
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(path, 0o444)

    @staticmethod
    def _completed_terminal_statuses(results: Any) -> dict[str, str]:
        roles = {"coordinator", "modeling", "protocol", "acceptance"}
        if (
            not isinstance(results, dict)
            or set(results) != roles
            or any(not isinstance(value, dict) or value.get("status") != "completed" for value in results.values())
        ):
            raise TeamConfigurationError("retained scope requires exactly four completed Agent statuses")
        return {role: "completed" for role in sorted(roles)}

    def _append_evidence(self, name: str, value: dict[str, Any]) -> None:
        if not self.run:
            return
        path = self.run.root / "evidence" / f"{name}.jsonl"
        envelope = {"recorded_at": datetime.now(UTC).isoformat(), **value}
        with path.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(envelope, ensure_ascii=False, sort_keys=True) + "\n"
            )
            stream.flush()
            os.fsync(stream.fileno())

    def _formal_ledger_identity(self) -> dict[str, dict[str, str]]:
        if not self._ledger:
            return {}
        config = getattr(self._ledger, "config", None)
        strict_sequence = bool(getattr(config, "strict_sequence", False))
        # Keep cleanup compatible with lightweight legacy test doubles that
        # predate the immutable config carrier while retaining the formal
        # requirement-ID check used by the previous implementation.
        if not strict_sequence:
            strict_sequence = (
                getattr(self._ledger, "requirement_id", None) == R2_3_005_REQUIREMENT_ID
            )
        if strict_sequence:
            return {"ledger_identity": self._ledger.identity}
        return {}

    def _append_team_transport_event(self, event: dict[str, object]) -> None:
        """Append one fixed-shape, sanitized report event in authoritative call order."""
        if not self.run:
            raise RuntimeError("Runner is not prepared")
        expected = {"agent", "tool", "status", "category", "ack", "recorded_at_ns"}
        if not isinstance(event, dict) or set(event) != expected:
            raise ValueError("invalid Team Transport event")
        agent = event["agent"]
        status = event["status"]
        category = event["category"]
        if (
            not isinstance(agent, str)
            or not agent
            or len(agent) > 64
            or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for char in agent)
            or event["tool"] != "report_task_result"
            or event["ack"] != "not_applicable"
            or not isinstance(event["recorded_at_ns"], int)
            or isinstance(event["recorded_at_ns"], bool)
            or event["recorded_at_ns"] <= 0
            or status not in {"rejected", "accepted"}
            or (
                status == "rejected"
                and category not in {"missing_modeling_handoff", "broker_rejection"}
            )
            or (status == "accepted" and category != "terminal_report_accepted")
        ):
            raise ValueError("invalid Team Transport event")
        path = self.run.root / "evidence" / "team-transport-events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        encoded = (json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        try:
            os.write(descriptor, encoded)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.chmod(path, 0o600)

    def _append_coordination_transport_event(self, event: dict[str, object]) -> None:
        """Persist only fixed coordination metadata after phase validation."""

        if not self.run:
            return
        expected = {
            "sender_id",
            "recipient_id",
            "message_kind",
            "text",
            "timestamp",
            "message_id",
            "terminal",
            "settles",
            "phase_event",
        }
        if not isinstance(event, dict) or set(event) != expected:
            return
        sender = event["sender_id"]
        recipient = event["recipient_id"]
        kind = event["message_kind"]
        text = event["text"]
        phase_event = event["phase_event"]
        if (
            not isinstance(sender, str)
            or not isinstance(recipient, str)
            or not isinstance(kind, str)
            or kind
            not in {
                "ready_for_acceptance",
                "silent_for_acceptance",
                "acceptance_start",
                "acceptance_verdict_route",
            }
            or not isinstance(text, str)
            or not isinstance(phase_event, dict)
        ):
            return
        safe_phase = {
            key: value
            for key, value in phase_event.items()
            if key not in {"text", "objective"}
        }
        self._append_evidence(
            "coordination",
            {
                "sender_id": sender,
                "recipient_id": recipient,
                "message_kind": kind,
                "message_id": event["message_id"],
                "timestamp": event["timestamp"],
                "terminal": False,
                "settles": False,
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "phase_event": safe_phase,
            },
        )

    @staticmethod
    def _atomic_json(path: Path, value: dict[str, Any]) -> None:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
