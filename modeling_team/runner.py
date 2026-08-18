"""Foreground single-run lifecycle and newline-delimited JSON outer protocol."""

from __future__ import annotations

import json
import hashlib
import os
import secrets
import shutil
import threading
import time
from copy import deepcopy
from datetime import UTC, datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping


from .contracts import (
    TeamConfiguration,
    TeamConfigurationError,
    digest_file,
    load_formal_team_configuration,
)
from .model_routing import (
    MODEL_PROFILE_DIRECTORY,
    TeamModelProfile,
    load_team_model_profile,
    preflight_codex_subscription_auth,
    preflight_profile_credentials,
    profile_requires_codex_subscription_auth,
)
from .formal_runs import (
    FORMAL_PROFILE_IDS,
    FORMAL_TASK_IDS,
    FormalRunContract,
    formal_run_contract_for,
    load_formal_run_configuration,
)
from .r23003_contract import (
    R2_3_003_TARGET_IDS,
    validate_r23003_candidate_declarations,
    validate_deletion_policy,
)
from .acceptance import (
    AcceptanceContractError,
    CoordinatorPhaseController,
    RunnerAcceptanceCarrier,
)
from .preflight import (
    normalize_scope_for_contract,
    run_existing_scope_preflight,
    run_prestart_preflight,
)
from .runtimes.base import RuntimeAdapter, RuntimeDelivery
from .candidate_progress import (
    FormalCandidateError,
    FormalCandidatePlatformContractError,
    FormalCandidateProgress,
    FormalCandidateProgressTimeout,
    FormalCandidateRoutingError,
    canonical_digest,
    formal_candidate_digests,
    validate_formal_conflict,
    validate_formal_receipt,
)
from .candidate_platform_gate import (
    CANDIDATE_RECEIPT_REGISTERED_KIND,
    CandidatePlatformGate,
    CandidatePlatformGateError,
    candidate_receipt_registered_notice,
)
from .candidate_publication import (
    CandidatePublicationError,
    StagedCandidatePublication,
    ValidatedCandidatePublication,
    stage_candidate_publication,
    validate_candidate_publication,
)
from .interventions import (
    IssueControl,
    IssueError,
    IssueResolution,
)
from .protocol_mcp_launch import (
    canonical_protocol_mcp_mode_contract,
    protocol_mcp_reasoner_contract,
)
from .protocol_mechanics import (
    ProtocolRetrievalFallbackError,
    build_candidate_conflict,
    build_candidate_receipt,
    build_candidate_item_evidence_map,
    build_existing_scope_candidate_conflict,
)
from .matrix_artifact import MatrixArtifactError, verify_matrix as verify_proof_matrix
from .start_ledger import (
    R2_3_002_REQUIREMENT_ID,
    R2_3_005_REQUIREMENT_ID,
    StartLedger,
    StartLedgerConfig,
    resolve_ledger_config,
)
from .transport_mcp import RoutingError, TeamTransportBroker, _call_terminal_report_guard
from .task_overlay import TaskInputOverlay, load_task_input_overlay
from .modeling_readonly import (
    MODELING_READ_TOOLS,
    ModelingContextGate,
    ModelingReadKeyLifecycle,
    ModelingReadProxy,
    ModelingReadError,
    canonical_digest as modeling_canonical_digest,
    _candidate_value as modeling_candidate_value,
)


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
    team_model_profile: TeamModelProfile | None = None
    formal_contract: FormalRunContract | None = None
    provider_credential_bindings: Mapping[str, Any] | None = None
    # Fixed safe label only (``chatgpt-subscription``); never a token, account,
    # auth cache path/digest, or login-status output.
    codex_subscription_auth_mode: str | None = None
    modeling_read_key_id: str | None = None
    modeling_read_proxy: ModelingReadProxy | None = None


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
        monotonic_clock: Callable[[], float] | None = None,
        deepseek_credential_path: Path | None = None,
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
        self.monotonic_clock = monotonic_clock or time.monotonic
        # This path is a constructor-only test seam.  Production callers leave it
        # unset and therefore bind the fixed external credential location.
        self.deepseek_credential_path = deepseek_credential_path
        # Safe conclusion of the Host ChatGPT subscription preflight; only the
        # fixed label from model_routing is ever stored here (no token, account,
        # cache path/digest, or login-status output).
        self.codex_subscription_auth_mode: str | None = None
        self.run: TeamRun | None = None
        self.transport: TeamTransportBroker | None = None
        self.scope: Any | None = None
        self._terminal_emitted = False
        self._runtime_failure_finalized = False
        self._terminal_handoffs_notified: set[tuple[str, str]] = set()
        self._terminal_handoff_sequence = 0
        # Acceptance settlement can be reached from both the foreground drain and
        # the formal Acceptance terminal-report guard. Serialize only that
        # finalization boundary; the method itself is idempotent after the lock.
        self._acceptance_settlement_lock = threading.Lock()
        self._acceptance_settlement_evidence_recorded = False
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
        self._candidate_progress: FormalCandidateProgress | None = None
        self._candidate_platform_gate: CandidatePlatformGate | None = None
        self._candidate_receipt_wakeup_sent: set[tuple[str, str]] = set()
        # One typed Protocol response is allowed for each active original
        # Modeling delivery.  The set is Runner-owned so a capability retry
        # cannot emit a second receipt/conflict for the same delivery.
        self._protocol_candidate_responses: dict[str, str] = {}
        self._protocol_candidate_receipt_digests: dict[str, str] = {}
        self._formal_workspace_version: str | None = None
        self._task_overlay: TaskInputOverlay | None = None
        self._validated_candidate_publication: ValidatedCandidatePublication | None = None
        self._candidate_publication: StagedCandidatePublication | None = None
        self._modeling_read_lifecycle: ModelingReadKeyLifecycle | None = None
        self._modeling_read_proxy: ModelingReadProxy | None = None
        self._modeling_context_gate: ModelingContextGate | None = None
        self._formal_failure_latched = False
        # Issue callbacks are invoked by the Broker/App-Server side.  They only
        # append to this queue; Runtime dispatch and evidence writes happen in
        # ``drain`` after all App-Server I/O locks have been released.
        self._issue_event_queue: list[dict[str, Any]] = []
        self._issue_event_lock = threading.Lock()
        # A Broker coordination callback runs while the Broker's emit lock is
        # held.  Queue the Acceptance start here and dispatch it from ``drain``
        # after the callback/observer stack has returned, so Runtime delivery
        # can never re-enter Broker locking.
        self._coordination_runtime_queue: list[dict[str, Any]] = []
        self._coordination_runtime_lock = threading.Lock()
        self._coordination_runtime_message_ids: set[str] = set()
        self._coordination_runtime_signal_keys: set[str] = set()
        self._issue_abort_requested = False
        self._issue_abort_terminal_failure_recorded = False

    @staticmethod
    def _safe_run_id(value: str) -> bool:
        import re

        return bool(re.fullmatch(r"[a-z0-9][a-z0-9-]{2,80}", value))

    @staticmethod
    def _write_frozen_bytes(path: Path, payload: bytes, *, mode: int = 0o444) -> None:
        """Write one immutable run-local input without following a symlink."""

        if path.exists() or path.is_symlink():
            raise TeamConfigurationError("frozen input path is already occupied")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, mode)
        try:
            remaining = memoryview(payload)
            while remaining:
                written = os.write(descriptor, remaining)
                if written <= 0:
                    raise OSError("frozen input write did not progress")
                remaining = remaining[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.chmod(path, mode)

    @staticmethod
    def _expected_matrix_binding(configuration: TeamConfiguration) -> dict[str, str] | None:
        """Project one proof marker from the loaded Task/Profile contract."""
        profile_binding = configuration.profile.expected_matrix_binding
        task_binding = configuration.task.expected_matrix_binding
        if profile_binding is not None and task_binding is not None and profile_binding != task_binding:
            raise TeamConfigurationError("Profile and Task expected_matrix_binding drift")
        return task_binding or profile_binding

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
        self,
        *,
        run_id: str,
        profile_path: Path,
        task_path: Path,
        scope: dict[str, str],
        task_overlay_path: Path | None = None,
        model_profile_id: str | None = None,
    ) -> TeamRun:
        if self.run is not None or not self._safe_run_id(run_id):
            raise TeamConfigurationError("unsafe or already attached run ID")
        config = load_formal_team_configuration(
            profile_path, task_path, root=self.repository_root
        )
        formal_contract = formal_run_contract_for(config)
        if formal_contract is None and (
            config.profile.profile_id in FORMAL_PROFILE_IDS
            or config.task.task_id in FORMAL_TASK_IDS
        ):
            raise TeamConfigurationError("unknown or cross-wired formal run contract")
        if formal_contract is not None and formal_contract.requirement_id == "R2.3-003":
            # Re-read through the closed registry so identity/path/asset checks
            # are performed before model/credential/preflight side effects.
            config, formal_contract = load_formal_run_configuration(
                profile_path, task_path, root=self.repository_root
            )
        formal_acceptance = formal_contract is not None
        # The model contract is the first formal gate after configuration
        # loading.  It performs only immutable package reads, so malformed,
        # partial, unsupported, inconsistent, or missing role declarations
        # cannot create a run root, reserve a ledger start, probe the platform,
        # start transport/capabilities, or invoke a process/child factory.
        selected_model_profile_id: str | None = None
        team_model_profile: TeamModelProfile | None = None
        if formal_contract is not None:
            selected_model_profile_id = (
                model_profile_id or formal_contract.default_model_profile_id
            )
            team_model_profile = load_team_model_profile(
                self.repository_root, selected_model_profile_id
            )
        elif model_profile_id is not None:
            raise TeamConfigurationError(
                "model profile selection requires a formal run contract"
            )
        provider_credential_bindings: dict[str, Any] | None = None
        defer_existing_credential_until_preflight = (
            formal_contract is not None
            and formal_contract.requirement_id == "R2.3-003"
            and formal_contract.is_existing
        )
        if formal_acceptance and not defer_existing_credential_until_preflight:
            # The Host ChatGPT subscription preflight runs only when the frozen
            # profile references the Codex built-in route, and strictly before
            # any external credential read, ledger reservation, run-root
            # creation, or Agent start.  A DeepSeek-only profile never triggers
            # it.  Only the fixed safe auth-mode label is retained.
            if profile_requires_codex_subscription_auth(team_model_profile):
                self.codex_subscription_auth_mode = preflight_codex_subscription_auth()
            provider_credential_bindings = preflight_profile_credentials(
                team_model_profile,
                deepseek_credential_path=self.deepseek_credential_path,
            )
        if config.task.schema_version == 2 and not self.freeze_started_at:
            raise TeamConfigurationError("v2 Task requires explicit freeze_started_at")
        task_overlay: TaskInputOverlay | None = None
        validated_publication: ValidatedCandidatePublication | None = None
        if task_overlay_path is not None:
            if not formal_acceptance:
                raise TeamConfigurationError("Task overlay is formal R2.3-005-only")
            task_overlay = load_task_input_overlay(
                task_overlay_path,
                root=self.repository_root,
                task_path=task_path,
                task=config.task,
            )
            validated_publication = validate_candidate_publication(task_overlay)
        if formal_acceptance:
            self._reject_formal_ledger_root_override()
        normalized_scope: dict[str, str] = dict(scope)
        if formal_contract is not None:
            normalized_scope = normalize_scope_for_contract(scope, formal_contract.scope_mode)
        root = self.repository_root / "workspaces" / "modeling-runs" / run_id
        if root.exists():
            raise TeamConfigurationError("run directory already exists")
        baseline = self._baseline_manifest(
            run_id=run_id,
            configuration=config,
            profile_path=profile_path,
            task_path=task_path,
            frozen_task_overlay=task_overlay,
            model_profile_id=selected_model_profile_id,
        )
        if formal_acceptance:
            self._assert_team_model_profile(baseline, team_model_profile)
        baseline_hash = StartLedger.baseline_hash(baseline)
        preflight_evidence: dict[str, Any] | None = None
        if formal_acceptance:
            # This is deliberately before ledger reservation, run-root creation,
            # scope construction, or any Agent start.  A second baseline read
            # closes the TOCTOU gap between inventory and reservation.
            if formal_contract is not None and formal_contract.is_existing:
                preflight_evidence = run_existing_scope_preflight(
                    repository_root=self.repository_root,
                    scope=normalized_scope,
                    base_url=self.canonical_base_url,
                    admin_key=self.canonical_admin_key,
                    probe=self.prestart_preflight,
                )
                live_scope = preflight_evidence.get("live") if isinstance(preflight_evidence, dict) else None
                if isinstance(live_scope, dict) and isinstance(
                    live_scope.get("workspace_version"), str
                ):
                    self._formal_workspace_version = live_scope["workspace_version"]
            else:
                preflight_evidence = run_prestart_preflight(
                    repository_root=self.repository_root,
                    base_url=self.canonical_base_url,
                    admin_key=self.canonical_admin_key,
                    probe=self.prestart_preflight,
                )
            if task_overlay_path is not None:
                task_overlay = load_task_input_overlay(
                    task_overlay_path,
                    root=self.repository_root,
                    task_path=task_path,
                    task=config.task,
                )
                validated_publication = validate_candidate_publication(task_overlay)
        if defer_existing_credential_until_preflight:
            # R2.3-003 binds an existing live scope.  Read the Host ChatGPT
            # login conclusion and the external model credentials only after
            # that live preflight has proved the retained Project/Ontology
            # state is still safe, while remaining before the profile/baseline
            # re-read, ledger reservation, run-root creation, and any Agent
            # start.
            if profile_requires_codex_subscription_auth(team_model_profile):
                self.codex_subscription_auth_mode = preflight_codex_subscription_auth()
            provider_credential_bindings = preflight_profile_credentials(
                team_model_profile,
                deepseek_credential_path=self.deepseek_credential_path,
            )
        if formal_acceptance:
            if team_model_profile is not None:
                # Two-read freeze: digest or parse drift between the initial
                # baseline read and this post-preflight re-read fails closed
                # before reservation and any Agent start.
                reloaded_profile = load_team_model_profile(
                    self.repository_root, team_model_profile.profile_id
                )
                if reloaded_profile != team_model_profile:
                    raise TeamConfigurationError("team model profile drifted during preflight")
            baseline_after_preflight = self._baseline_manifest(
                run_id=run_id,
                configuration=config,
                profile_path=profile_path,
                task_path=task_path,
                frozen_task_overlay=task_overlay,
                model_profile_id=selected_model_profile_id,
            )
            self._assert_team_model_profile(baseline_after_preflight, team_model_profile)
            if StartLedger.baseline_hash(baseline_after_preflight) != baseline_hash:
                raise TeamConfigurationError("baseline manifest drifted during preflight")
        # The proof gate belongs to the loaded Task/Profile contract, not to the
        # formal R2.3-005 workflow flag.  Archived R2.3-002 runs still carry the
        # expected matrix binding and must project that same gate into TeamRun;
        # an unbound R2.3-005 run remains ordinary/non-proof.
        expected_binding = self._expected_matrix_binding(config)
        gate_binding = (
            self._resolve_expected_matrix_binding(expected_binding)
            if expected_binding
            else None
        )
        if config.task.schema_version == 2:
            ledger_config = resolve_ledger_config(
                formal_contract.ledger_requirement_id
                if formal_contract is not None and formal_contract.ledger_requirement_id
                else R2_3_002_REQUIREMENT_ID
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
        self.run = TeamRun(
            run_id,
            root,
            config,
            normalized_scope,
            gate_binding=gate_binding,
            team_model_profile=team_model_profile,
            formal_contract=formal_contract,
            provider_credential_bindings=provider_credential_bindings,
            codex_subscription_auth_mode=self.codex_subscription_auth_mode,
        )
        if formal_contract is not None and formal_contract.requirement_id == "R2.3-003":
            try:
                self._modeling_context_gate = ModelingContextGate(
                    run_id=run_id,
                    project_id=normalized_scope["project_id"],
                    ontology_id=normalized_scope["ontology_id"],
                )
            except (KeyError, ModelingReadError) as exc:
                raise TeamConfigurationError("R2.3-003 Modeling context gate scope is invalid") from exc
        self._task_overlay = task_overlay
        self._validated_candidate_publication = validated_publication
        self._candidate_publication = (
            stage_candidate_publication(task_overlay, validated_publication, run_root=root)
            if task_overlay is not None and validated_publication is not None
            else None
        )
        self._candidate_progress = (
            FormalCandidateProgress(
                clock=self.monotonic_clock,
                timeout_seconds=config.profile.parameters.get(
                    "candidate_progress_timeout_seconds", 120.0
                ),
                allow_post_receipt_revision=(
                    formal_contract is not None
                    and formal_contract.requirement_id == "R2.3-003"
                ),
                # R2.3-008 start7: keep the envelope gate aligned with
                # candidate registration so an integer revision for any other
                # task is a typed first-delivery rejection, not a post-gate
                # run-killing registration error.
                integer_revisions=(
                    formal_contract is not None
                    and formal_contract.requirement_id == "R2.3-003"
                ),
            )
            if formal_acceptance
            else None
        )
        self._candidate_platform_gate = (
            CandidatePlatformGate.ensure(root / "candidate-gate")
            if formal_acceptance
            else None
        )
        self._protocol_candidate_responses = {}
        self._protocol_candidate_receipt_digests = {}
        self._candidate_receipt_wakeup_sent = set()
        self._formal_failure_latched = False
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
            candidate_publisher=(
                self._publish_staged_candidate
                if self._candidate_publication is not None
                else None
            ),
            candidate_receipt_builder=(
                self._build_protocol_candidate_receipt
                if formal_acceptance
                else None
            ),
            candidate_conflict_builder=(
                self._build_protocol_candidate_conflict
                if formal_acceptance
                else None
            ),
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
        if task_overlay is None:
            shutil.copyfile(task_path, root / "task.snapshot.yaml")
        else:
            self._write_frozen_bytes(root / "task.snapshot.yaml", task_overlay.base_task_bytes)
            self._write_frozen_bytes(
                root / "task-overlay.snapshot.yaml",
                task_overlay.overlay_bytes,
            )
            self._write_frozen_bytes(
                root / "candidate-publication-manifest.json",
                json.dumps(
                    task_overlay.manifest(),
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode("utf-8"),
            )
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

    @staticmethod
    def _assert_team_model_profile(
        baseline: dict[str, Any], team_model_profile: TeamModelProfile | None
    ) -> None:
        if team_model_profile is None:
            raise TeamConfigurationError("formal team model profile is unavailable")
        binding = baseline.get("team_model_profile")
        if (
            not isinstance(binding, dict)
            or binding.get("profile_id") != team_model_profile.profile_id
            or binding.get("path") != team_model_profile.relative_path
            or binding.get("sha256") != team_model_profile.digest
            or binding.get("roles") != team_model_profile.as_dict()["roles"]
        ):
            raise TeamConfigurationError("formal team model profile digest drifted")

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
        if not isinstance(questions, list) or not questions:
            raise TeamConfigurationError("acceptance standard must declare at least one competency question")
        normalized_questions: list[dict[str, str]] = []
        source_paths_by_question: dict[str, list[str]] = {}
        question_ids: set[str] = set()
        for item in questions:
            if not isinstance(item, dict) or set(item) != {"id", "question", "approved_source_paths"}:
                raise TeamConfigurationError("acceptance standard competency question fields drift")
            if not isinstance(item["id"], str) or not isinstance(item["question"], str) or not item["id"] or not item["question"]:
                raise TeamConfigurationError("acceptance standard competency question is invalid")
            if item["id"] in question_ids:
                raise TeamConfigurationError("acceptance standard competency question IDs are duplicated")
            paths = item["approved_source_paths"]
            if not isinstance(paths, list) or not paths or any(not isinstance(path, str) for path in paths):
                raise TeamConfigurationError("acceptance standard source paths are invalid")
            question_ids.add(item["id"])
            normalized_questions.append({"id": item["id"], "question": item["question"]})
            source_paths_by_question[item["id"]] = sorted(paths)
        requirement_id = formal_run_contract_for(configuration).requirement_id if formal_run_contract_for(configuration) else None
        unknown_policy = standard.get("unknown_policy")
        deletion = None
        if requirement_id == "R2.3-003":
            try:
                deletion = validate_deletion_policy(unknown_policy)
            except ValueError as exc:
                raise TeamConfigurationError(str(exc)) from exc
            if tuple(item["semantic_id"] for item in deletion["targets"]) != R2_3_003_TARGET_IDS:
                raise TeamConfigurationError("R2.3-003 acceptance target IDs drift")
        elif unknown_policy != "preserve-explicit-unknown":
            raise TeamConfigurationError("formal create acceptance unknown policy drifts")
        artifact = {"path": parameter, "digest": digest_file(standard_path)}
        return {
            "quality_standard_ref": str(standard.get("requirement_ref", "")),
            "quality_standard_digest": artifact["digest"],
            "quality_standard_artifact": artifact,
            "unknown_policy": deletion if deletion is not None else unknown_policy,
            "deletion_policy": deletion,
            "competency_questions": normalized_questions,
            "approved_source_paths_by_question": source_paths_by_question,
            "question_count": len(normalized_questions),
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
        task_overlay_path: Path | None = None,
        frozen_task_overlay: TaskInputOverlay | None = None,
        model_profile_id: str | None = None,
    ) -> dict[str, Any]:
        if task_overlay_path is not None and frozen_task_overlay is not None:
            raise TeamConfigurationError("Task overlay cannot be both live and frozen")
        files = {
            "runner": self.repository_root / "modeling_team/runner.py",
            "acceptance_contract": self.repository_root / "modeling_team/acceptance.py",
            "acceptance_runtime": self.repository_root / "modeling_team/acceptance_runtime.py",
            "capability_mcp": self.repository_root / "modeling_team/capability_mcp.py",
            "task_overlay": self.repository_root / "modeling_team/task_overlay.py",
            "candidate_publication": self.repository_root / "modeling_team/candidate_publication.py",
            "read_proxy_mcp": self.repository_root / "modeling_team/read_proxy_mcp.py",
            "report_sink_mcp": self.repository_root / "modeling_team/report_sink_mcp.py",
            "preflight": self.repository_root / "modeling_team/preflight.py",
            "codex_adapter": self.repository_root / "modeling_team/runtimes/codex.py",
            "team_transport": self.repository_root / "modeling_team/transport_mcp.py",
            "team_transport_interventions": self.repository_root / "modeling_team/interventions.py",
            "platform_scope": self.repository_root / "modeling_team/platform_scope.py",
            "protocol_mcp_launch": self.repository_root / "modeling_team/protocol_mcp_launch.py",
            "candidate_platform_gate": self.repository_root / "modeling_team/candidate_platform_gate.py",
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
        task_overlay = frozen_task_overlay
        if task_overlay is None and task_overlay_path is not None:
            task_overlay = load_task_input_overlay(
                task_overlay_path,
                root=self.repository_root,
                task_path=task_path,
                task=configuration.task,
            )
            validate_candidate_publication(task_overlay)
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
        formal_contract = formal_run_contract_for(configuration)
        formal_acceptance_contract = formal_contract is not None
        if formal_acceptance_contract:
            assert formal_contract is not None
            selected_profile_id = (
                model_profile_id or formal_contract.default_model_profile_id
            )
            files["team_model_profile"] = (
                self.repository_root
                / MODEL_PROFILE_DIRECTORY
                / f"{selected_profile_id}.yaml"
            )
            if formal_contract.requirement_id == "R2.3-003":
                files["modeling_readonly"] = self.repository_root / "modeling_team/modeling_readonly.py"
        digests = {name: digest_file(path) for name, path in sorted(files.items())}
        if task_overlay is not None:
            digests["task_input_overlay"] = task_overlay.sha256
            digests["candidate_publication_source"] = (
                task_overlay.candidate_publication.sha256
            )
        runner_capability_roles = {
            "protocol": [
                "protocol_list_platform_artifacts",
                "protocol_build_acceptance_stage_handoff",
            ],
            "coordinator": [
                "coordinator_build_acceptance_ticket_draft",
                "coordinator_publish_acceptance_ticket",
                "coordinator_get_verdict",
            ],
            "acceptance": [
                "acceptance_get_ticket",
                "acceptance_child_start",
                "acceptance_child_get_report",
                "acceptance_child_recycle",
                "acceptance_get_failure_record",
                "build_acceptance_verdict",
                "submit_acceptance_result",
                "acceptance_get_verdict",
            ],
        }
        if formal_acceptance_contract:
            runner_capability_roles["coordinator"].insert(
                1, "coordinator_build_acceptance_ticket_draft_from_delivery"
            )
        if task_overlay is not None:
            runner_capability_roles["modeling"] = ["modeling_publish_staged_candidate"]
        baseline = {
            "run_id": run_id,
            **(
                {"task_input_overlay": task_overlay.manifest()}
                if task_overlay is not None
                else {}
            ),
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
                "transport.staged_interventions": digests["team_transport_interventions"],
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
                "runner.task_overlay": digests["task_overlay"],
                "runner.candidate_publication": digests["candidate_publication"],
                "runner.acceptance_child_runtime": digests["acceptance_runtime"],
                "runner.acceptance_read_proxy": digests["read_proxy_mcp"],
                **(
                    {"runner.modeling_read_surface": digests["modeling_readonly"]}
                    if formal_contract is not None and formal_contract.requirement_id == "R2.3-003"
                    else {}
                ),
                "runner.acceptance_report_sink": digests["report_sink_mcp"],
                "runner.coordination_phase_callback": digests["runner"],
                "p2_protocol_driver.main": digests["p2_protocol_driver"],
                "p2a_protocol_driver.main": digests["p2a_protocol_driver"],
            },
            "runtime_contract": {
                "team_transport": {
                    "server": "team_transport",
                    "command": "/usr/bin/python3",
                    "args": ["/agent/home/transport_mcp.py"],
                    "source_path": "modeling_team/transport_mcp.py",
                    "sha256": digests["team_transport"],
                    "staged_dependency": {
                        "source_path": "modeling_team/interventions.py",
                        "staged_path": "/agent/home/interventions.py",
                        "sha256": digests["team_transport_interventions"],
                        "mode": "0444",
                    },
                },
                "runner_capability_mcp": {
                    "server": "runner_capability",
                    "source_path": "modeling_team/capability_mcp.py",
                    "sha256": digests["capability_mcp"],
                    "roles": runner_capability_roles,
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
                        "translate_candidate_to_batches",
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
        if formal_acceptance_contract:
            profile = load_team_model_profile(self.repository_root, selected_profile_id)
            if profile.digest != digests["team_model_profile"]:
                raise TeamConfigurationError("formal team model profile digest is inconsistent")
            # Safe projection only: identity, repo-relative path, source digest,
            # and per-role provider/model/effort.  No endpoint, credential
            # path/value/digest, or provider free text.
            baseline["team_model_profile"] = profile.as_dict()
            if formal_contract.requirement_id == "R2.3-003":
                baseline["runtime_contract"]["modeling_read_proxy"] = {
                    "server": "modeling_read_proxy",
                    "source_path": "modeling_team/modeling_readonly.py",
                    "bridge_source_path": "modeling_team/read_proxy_mcp.py",
                    "sha256": digests["modeling_readonly"],
                    "bridge_sha256": digests["read_proxy_mcp"],
                    "tools": list(MODELING_READ_TOOLS),
                    "socket_mode": "0600",
                    "token_file_mode": "0400",
                    "scope": "exact-project-ontology",
                }
        return baseline

    @classmethod
    def preview_baseline(
        cls,
        *,
        repository_root: Path,
        run_id: str,
        profile_path: Path,
        task_path: Path,
        task_overlay_path: Path | None = None,
        model_profile_id: str | None = None,
    ) -> tuple[dict[str, Any], str]:
        """Compute the prepare-time binding without creating any run or ledger state."""
        if not cls._safe_run_id(run_id):
            raise TeamConfigurationError("unsafe or already attached run ID")
        configuration = load_formal_team_configuration(
            profile_path, task_path, root=repository_root
        )
        formal_contract = formal_run_contract_for(configuration)
        if model_profile_id is not None and formal_contract is None:
            raise TeamConfigurationError(
                "model profile selection requires a formal run contract"
            )
        if formal_contract is not None:
            configuration, _ = load_formal_run_configuration(
                profile_path, task_path, root=repository_root
            )
        elif (
            configuration.profile.profile_id in FORMAL_PROFILE_IDS
            or configuration.task.task_id in FORMAL_TASK_IDS
        ):
            raise TeamConfigurationError("unknown or cross-wired formal run contract")
        probe = object.__new__(cls)
        probe.repository_root = repository_root
        manifest = probe._baseline_manifest(
            run_id=run_id,
            configuration=configuration,
            profile_path=profile_path,
            task_path=task_path,
            task_overlay_path=task_overlay_path,
            model_profile_id=model_profile_id,
        )
        return manifest, StartLedger.baseline_hash(manifest)

    def _formal_coordination_enabled(self) -> bool:
        if not self.run:
            return False
        if getattr(self.run, "formal_contract", None) is not None:
            return True
        configuration = getattr(self.run, "configuration", None)
        task = getattr(configuration, "task", None)
        profile = getattr(configuration, "profile", None)
        return bool(
            getattr(task, "schema_version", 1) == 2
            and (
                getattr(task, "task_id", None)
                in {"r2-3-005-formal-acceptance", "r2-3-003-existing-scope-incremental"}
                or getattr(profile, "profile_id", None)
                in {"r2-3-005-modeling-team", "r2-3-003-modeling-team"}
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
            # Formal R2.3-005 keeps Coordinator as the sole round selector,
            # while the Runner-owned carrier validates that selection before
            # the generic controller changes phase or the observer queues the
            # Acceptance delivery.  Reject the generic controller's own
            # out-of-phase/stale-generation cases first so a rejected request
            # cannot append even a passive CQ2 revalidation record.
            formal_sequential = (
                self._formal_coordination_enabled()
                and self.acceptance is not None
                and getattr(self.acceptance, "_ticket_policy", None) is not None
            )
            if formal_sequential:
                phase = getattr(self.coordinator_phase, "phase", None)
                phase_value = getattr(phase, "value", phase)
                controller = self.coordinator_phase
                if (
                    sender_id != controller.coordinator_id
                    or phase_value != "WAITING_ACCEPTANCE"
                    or not isinstance(text, str)
                    or not text
                    or isinstance(generation, bool)
                    or not isinstance(generation, int)
                    or generation != controller.generation
                ):
                    return controller.start_acceptance_round(
                        sender_id=sender_id,
                        round_id=text,
                        generation=generation,
                    )
                self.acceptance.validate_coordinator_acceptance_start(round_id=text)
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
        self,
        agent_id: str,
        already_synchronized: bool = False,
        status: str = "completed",
    ) -> bool:
        """Compose the existing Runtime guard with the formal Coordinator terminal gate.

        The Runtime guard still owns protocol retrieval safety.  For the formal four-role
        run, Acceptance and Coordinator are additionally blocked until Acceptance has
        persisted two same-state PASS verdicts, reclaimed both child pairs, and committed
        settlement CAS/readback.  No model/SSE/``agent_end`` semantics are changed here.
        """

        issue_ledger = self._issue_ledger()
        if issue_ledger is not None and issue_ledger.pending:
            return True
        adapter_guard = getattr(self.adapter, "terminal_report_blocked", None)
        if callable(adapter_guard):
            try:
                if _call_terminal_report_guard(
                    adapter_guard,
                    agent_id,
                    already_synchronized,
                    status,
                ):
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
                # verdict. Only a completed report may cross this boundary, and
                # the Delivery/Runner path must first perform the complete
                # cleanup + CAS/readback settlement transition. Incomplete,
                # failed, and blocked reports remain live even if a stale carrier
                # happens to expose a settled flag.
                if status != "completed":
                    return True
                self._finalize_acceptance_if_ready()
                return self.acceptance is None or not self.acceptance.is_settled
        return False

    def _finalize_acceptance_if_ready(self) -> None:
        """Commit explicit Acceptance settlement before Coordinator may report terminal."""

        if not self._formal_coordination_enabled() or self.acceptance is None:
            return
        settlement_ready = getattr(self.acceptance, "settlement_ready", None)
        if not callable(settlement_ready):
            # Lightweight legacy test doubles and offline adapters may expose
            # only ``is_settled``. They cannot claim the settlement boundary, so
            # leave the terminal guard blocked without invoking a partial path.
            return
        with self._acceptance_settlement_lock:
            # Both checks intentionally happen after acquiring the shared lock.
            # A concurrent guard/drain pair must observe the settled carrier and
            # return without a second CAS, settlement artifact, or evidence row.
            if self.acceptance.is_settled or not settlement_ready():
                return
            try:
                receipt = self.acceptance.settle()
            except AcceptanceContractError:
                # A state reader may have observed drift. The carrier records the
                # invalidation and remains non-settled; Coordinator cannot pass its guard.
                return
            if not self._acceptance_settlement_evidence_recorded:
                self._append_evidence(
                    "acceptance-settlement",
                    {
                        "status": receipt.get("status"),
                        "settlement_cas": receipt.get("settlement_cas"),
                        "final_readback": receipt.get("final_readback"),
                    },
                )
                self._acceptance_settlement_evidence_recorded = True

    def _consume_runtime_failures(self) -> list[tuple[str, dict[str, Any]]]:
        """Read the adapter-owned typed failure queue with legacy fallback."""

        reader = getattr(self.adapter, "consume_runtime_failures", None)
        if callable(reader):
            failures = reader()
            return list(failures) if isinstance(failures, (list, tuple)) else []
        # Older deterministic adapters expose only the inactivity projection.
        legacy = getattr(self.adapter, "consume_inactivity_failures", None)
        if callable(legacy):
            failures = legacy()
            return list(failures) if isinstance(failures, (list, tuple)) else []
        return []

    def _finalize_runtime_failure(
        self, failures: list[tuple[str, dict[str, Any]]]
    ) -> list[dict[str, Any]]:
        """Settle one typed runtime failure exactly once and stop the roster."""

        if self._runtime_failure_finalized or not failures:
            return []
        self._runtime_failure_finalized = True
        agent_id, detail = failures[0]
        safe_detail = dict(detail) if isinstance(detail, dict) else {}
        self._append_evidence(
            "runtime-failure",
            {"agent_id": agent_id, **safe_detail},
        )
        self.record_terminal_failure("runtime/infrastructure", False)
        cleanup = self.cleanup()
        self._state(
            "TERMINAL_REPORT_COMPLETE",
            runtime_failure=True,
            agent_id=agent_id,
            role=safe_detail.get("role"),
            reason=safe_detail.get("reason"),
        )
        return [
            {
                "type": "runtime-failure",
                "agent_id": agent_id,
                "role": safe_detail.get("role"),
                "reason": safe_detail.get("reason"),
                "cleanup": cleanup,
            }
        ]

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
                if self._is_r23003_modeling_run():
                    self._ensure_modeling_read_surface()
            role_agents = {
                agent.package.role: agent.agent_id for agent in self.run.configuration.profile.agents
            }
            transport_event_lock = threading.Lock()

            def transport_event_observer(event: dict[str, object]) -> None:
                with transport_event_lock:
                    self._append_team_transport_event(event)

            def issue_event_callback(event: dict[str, object]) -> None:
                if not isinstance(event, dict):
                    return
                with self._issue_event_lock:
                    self._issue_event_queue.append(deepcopy(event))

            terminal_dependencies = {
                role_agents["protocol"]: {role_agents["modeling"]},
                role_agents["coordinator"]: {
                    role_agents["modeling"],
                    role_agents["protocol"],
                    role_agents["acceptance"],
                },
            }
            if formal_coordination:
                # Formal Acceptance is the semantic gate for the Modeling
                # terminal. Keep the historical non-formal dependency graph
                # unchanged; only the formal four-role run serializes the
                # final path Acceptance -> Modeling -> Protocol -> Coordinator.
                terminal_dependencies[role_agents["modeling"]] = {
                    role_agents["acceptance"]
                }
            self.transport = TeamTransportBroker(
                self.run.root / "transport" / "broker",
                set(self.run.configuration.profile.communication),
                terminal_dependencies=terminal_dependencies,
                modeling_agent_id=role_agents["modeling"],
                coordinator_agent_id=role_agents["coordinator"],
                terminal_report_guard=self._terminal_report_guard,
                transport_event_observer=transport_event_observer,
                coordination_phase_callback=(
                    self._coordination_phase_callback if formal_coordination else None
                ),
                coordination_event_observer=(
                    self._coordination_transport_event_observer if formal_coordination else None
                ),
                issue_escalation_enabled=formal_coordination,
                issue_event_callback=issue_event_callback if formal_coordination else None,
                pre_send_validator=(
                    self._validate_modeling_transport_send
                    if self._is_r23003_modeling_run()
                    else None
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
                try:
                    self.adapter.start_task(
                        agent.agent_id,
                        self._task_text(agent.package.role),
                        [str(path) for path in agent.package.required_skills],
                        roster,
                    )
                except Exception:
                    failures = self._consume_runtime_failures()
                    if failures:
                        self._state("FAILED")
                        self._finalize_runtime_failure(failures)
                        return
                    raise
                failures = self._consume_runtime_failures()
                if failures:
                    self._state("FAILED")
                    self._finalize_runtime_failure(failures)
                    return
            self._state("RUNNING", identities=[item.agent_id for item in identities])
        except Exception:
            failures = self._consume_runtime_failures()
            if failures:
                self._state("FAILED")
                self._finalize_runtime_failure(failures)
                return
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
        if expected_gate is None:
            raise TeamConfigurationError(
                "candidate evidence-map gate is disabled without expected_matrix_binding"
            )
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
        terminal_evidence: dict[str, Any] | None = None,
    ) -> None:
        if not self.run or not self._ledger:
            return
        self._ledger.terminal_failure(
            self.run.run_id,
            classification,
            complete_modeling_quality_result,
            repair_baseline_hash,
            terminal_evidence,
        )
        self._append_evidence(
            "terminal-classification",
            {
                "classification": classification,
                "complete_modeling_quality_result": complete_modeling_quality_result,
                "repair_baseline_hash": repair_baseline_hash,
                **({"terminal_evidence": terminal_evidence} if terminal_evidence is not None else {}),
            },
        )

    def _record_issue_abort_terminal_failure(
        self,
        issue: Any,
        cleanup: dict[str, Any],
    ) -> None:
        """Reconcile a zero-mutation 003 issue abort into the append-only ledger."""

        if self._issue_abort_terminal_failure_recorded:
            return
        if not self.run or not self._ledger:
            return
        contract = formal_run_contract_for(self.run.configuration)
        if contract is None or contract.requirement_id != "R2.3-003":
            # R2.3-005 retains its existing issue/cleanup path; this narrow
            # reconciliation is only needed for the existing-scope ledger.
            return
        if issue is None or getattr(issue, "run_id", None) != self.run.run_id:
            raise TeamConfigurationError("issue abort run binding is invalid")
        raw_mutation_state = getattr(issue, "mutation_state", None)
        if not (
            isinstance(raw_mutation_state, str)
            and (
                raw_mutation_state == "zero-mutation"
                or raw_mutation_state.startswith("zero-mutation;")
            )
        ):
            raise TeamConfigurationError("issue abort lacks zero-mutation evidence")
        # Keep explanatory issue prose outside the strict ledger field.
        mutation_state = "zero-mutation"
        if not isinstance(cleanup, dict):
            raise TeamConfigurationError("issue abort cleanup evidence is invalid")
        acceptance = cleanup.get("acceptance")
        scope = cleanup.get("scope")
        if (
            not isinstance(acceptance, dict)
            or acceptance.get("status") != "aborted"
            or acceptance.get("zero_child_residue") is not True
            or not isinstance(scope, dict)
            or scope.get("cleanup_blocker")
            or scope.get("no_in_flight_attempts") is not True
        ):
            raise TeamConfigurationError("issue abort cleanup is not zero-mutation clean")
        before = scope.get("existing_context_before")
        after = scope.get("existing_context_after")
        if isinstance(before, dict) and isinstance(after, dict) and before != after:
            raise TeamConfigurationError("issue abort existing scope changed during cleanup")
        baseline_hash = self.run.baseline_hash
        if not isinstance(baseline_hash, str) or not baseline_hash:
            raise TeamConfigurationError("issue abort baseline binding is unavailable")
        issue_payload = {
            "run_id": self.run.run_id,
            "issue_id": issue.issue_id,
            "mutation_state": mutation_state,
            "failing_operation": issue.failing_operation,
            "error": issue.error,
        }
        evidence_payload = {
            "run_id": self.run.run_id,
            "baseline_hash": baseline_hash,
            "classification": "platform-contract",
            "mutation_state": "zero-mutation",
            "issue_id": issue.issue_id,
            "issue_digest": canonical_digest(issue_payload),
            "cleanup_digest": canonical_digest(cleanup),
            "evidence_path": "evidence/terminal-reconciliation.jsonl",
        }
        evidence_digest = canonical_digest(evidence_payload)
        terminal_evidence = {
            "run_id": self.run.run_id,
            "baseline_hash": baseline_hash,
            "classification": "platform-contract",
            "mutation_state": "zero-mutation",
            "issue_id": issue.issue_id,
            "evidence_path": evidence_payload["evidence_path"],
            "evidence_digest": evidence_digest,
        }
        self._append_evidence(
            "terminal-reconciliation",
            {**evidence_payload, "evidence_digest": evidence_digest},
        )
        try:
            self.record_terminal_failure(
                "platform-contract",
                False,
                terminal_evidence=terminal_evidence,
            )
        except Exception as exc:
            raise TeamConfigurationError(
                "issue-abort terminal reconciliation failed after cleanup evidence was persisted"
            ) from exc
        self._issue_abort_terminal_failure_recorded = True

    def _publish_staged_candidate(self, modeling_id: str) -> dict[str, Any]:
        """Publish one prevalidated candidate through ordinary Team Transport."""

        if self._candidate_publication is None or self.transport is None:
            raise CandidatePublicationError("staged candidate publication is unavailable")
        if self._modeling_context_gate is not None:
            self._modeling_context_gate.assert_open()
        role_ids = self._formal_coordination_role_ids()
        receipt = self._candidate_publication.publish(
            actor_id=modeling_id,
            modeling_id=role_ids["modeling"],
            protocol_id=role_ids["protocol"],
            send=self.transport.send,
        )
        identity = modeling_candidate_value(self._candidate_publication.candidate_text)
        if identity is not None and self._modeling_context_gate is not None:
            self._modeling_context_gate.bind_candidate(
                str(receipt.get("delivery_id")), modeling_canonical_digest(identity)
            )
        return receipt

    def _validate_modeling_transport_send(
        self,
        sender_id: str,
        recipient_id: str,
        text: str,
        expects_reply: bool,
        reply_to_delivery_id: str | None,
    ) -> None:
        """Keep an R2.3-003 candidate behind the immutable context receipt gate."""

        if not self._is_r23003_modeling_run() or self.run is None:
            return
        role_ids = self._formal_coordination_role_ids()
        if sender_id != role_ids.get("modeling") or recipient_id != role_ids.get("protocol"):
            return
        if self._modeling_context_gate is None:
            raise RoutingError("R2.3-003 Modeling context gate is unavailable")
        try:
            self._modeling_context_gate.assert_open()
        except ModelingReadError as exc:
            raise RoutingError("candidate publication requires an accepted Modeling context receipt") from exc

        # Modeling may open the first candidate request with a fresh reply slot,
        # or replace an accepted receipt only by replying to the currently
        # validated standalone Protocol conflict.  A receipt/conflict payload,
        # foreign reply anchor, stale conflict anchor, and partial revision are
        # all rejected before Team Transport can mutate its reply table.
        candidate: Mapping[str, Any] | None = None
        if isinstance(text, str):
            try:
                decoded = json.loads(text)
            except (TypeError, json.JSONDecodeError):
                decoded = None
            if isinstance(decoded, Mapping):
                candidate = decoded if modeling_candidate_value(text) is not None else None

        if not expects_reply:
            if candidate is not None:
                raise RoutingError("R2.3-003 candidate publication must open a fresh reply slot")
            return
        if candidate is None:
            raise RoutingError("R2.3-003 Modeling reply must be a complete candidate")

        progress = self._candidate_progress
        pending = progress.pending if progress is not None else None
        if reply_to_delivery_id is None:
            # The initial candidate is the only fresh Modeling->Protocol
            # candidate request.  Once FormalCandidateProgress has an identity,
            # a second fresh request is stale rather than a new slot.
            if pending is not None:
                raise RoutingError("R2.3-003 fresh candidate slot is already occupied")
            try:
                formal_candidate_digests(candidate)
            except FormalCandidateError as exc:
                raise RoutingError("R2.3-003 candidate is not a complete formal candidate") from exc
            return

        if (
            pending is None
            or progress is None
            or progress.state != "awaiting_revision"
            or pending.conflict_delivery_id != reply_to_delivery_id
        ):
            raise RoutingError(
                "R2.3-003 revision must reply to the current standalone Protocol conflict"
            )
        try:
            formal_candidate_digests(candidate)
        except FormalCandidateError as exc:
            raise RoutingError("R2.3-003 revision is not a complete formal candidate") from exc

    def _is_r23003_modeling_run(self) -> bool:
        if self.run is None:
            return False
        contract = formal_run_contract_for(self.run.configuration)
        return contract is not None and contract.requirement_id == "R2.3-003"

    def _observe_modeling_context(
        self, response: Mapping[str, Any], call_receipt: Any
    ) -> None:
        gate = self._modeling_context_gate
        if gate is None:
            raise ModelingReadError("R2.3-003 Modeling context gate is unavailable")
        if gate.receipt is None or gate.state == "closed":
            gate.observe(response, call_receipt=call_receipt)
        else:
            gate.revalidate(response, call_receipt=call_receipt)
        self._append_evidence(
            "modeling-context-receipt",
            {
                "receipt_digest": gate.receipt.receipt_digest if gate.receipt else None,
                "workspace_version": gate.receipt.workspace_version if gate.receipt else None,
                "revalidation_receipt_digest": (
                    gate.revalidation_receipt.get("revalidation_receipt_digest")
                    if gate.revalidation_receipt
                    else None
                ),
                "project_id": gate.project_id,
                "ontology_id": gate.ontology_id,
            },
        )

    def _ensure_modeling_read_surface(self) -> None:
        """Create the short-lived Modeling read key and local policy proxy."""

        if not self._is_r23003_modeling_run() or self.run is None:
            return
        if self.scope is None:
            raise ModelingReadError("Modeling read surface requires a prepared PlatformScope")
        if self._modeling_read_lifecycle is not None:
            return
        lifecycle = ModelingReadKeyLifecycle(self.scope, repository_root=self.repository_root)
        self._modeling_read_lifecycle = lifecycle
        record = None
        proxy = None
        try:
            record = lifecycle.create(
                project_id=self.run.scope["project_id"],
                ontology_id=self.run.scope["ontology_id"],
                run_id=self.run.run_id,
            )
            socket_path = self.run.root / "modeling-read-proxy.sock"
            if len(str(socket_path)) >= 100:
                import hashlib as _hashlib

                socket_path = Path("/tmp") / (
                    "mt-mr-" + _hashlib.sha256(str(socket_path).encode()).hexdigest()[:24] + ".sock"
                )
            proxy = ModelingReadProxy(
                socket_path=socket_path,
                token=secrets.token_urlsafe(24),
                read_key=lifecycle.plaintext_for(record.key_id),
                project_id=record.project_id,
                ontology_id=record.ontology_id,
                forward=lifecycle.forwarder_for(record.key_id),
                on_context=self._observe_modeling_context,
            )
            proxy.start()
        except Exception:
            if proxy is not None:
                proxy.destroy()
            if record is not None:
                try:
                    lifecycle.revoke(record.key_id)
                except Exception:
                    pass
            self._modeling_read_lifecycle = None
            raise
        assert record is not None and proxy is not None
        self._modeling_read_proxy = proxy
        self.run.modeling_read_key_id = record.key_id
        self.run.modeling_read_proxy = proxy
        self._append_evidence(
            "modeling-read-key",
            {
                "key_id": record.key_id,
                "key_digest": record.key_digest,
                "project_id": record.project_id,
                "ontology_id": record.ontology_id,
                "allowed_tools": list(MODELING_READ_TOOLS),
                "proxy": proxy.receipt.__dict__,
            },
        )

    def _active_protocol_candidate(
        self,
        protocol_id: str,
        delivery_id: str,
        *,
        response_kind: str,
    ) -> tuple[dict[str, Any], Any]:
        """Resolve one live formal candidate without accepting model-supplied bytes."""

        if not self._formal_coordination_enabled() or self.run is None:
            raise TeamConfigurationError("typed candidate binding is unavailable")
        if self.transport is None or self.acceptance is None or not self.acceptance.is_live:
            raise TeamConfigurationError("typed candidate binding is not active")
        role_ids = self._formal_coordination_role_ids()
        if protocol_id != role_ids["protocol"]:
            raise TeamConfigurationError("typed candidate protocol identity is not bound")
        if not isinstance(delivery_id, str) or not delivery_id:
            raise TeamConfigurationError("typed candidate delivery_id is invalid")
        progress = self._candidate_progress
        identity = progress.identity if progress is not None else None
        candidate = progress.candidate if progress is not None else None
        if identity is None or candidate is None:
            raise TeamConfigurationError("typed candidate has no active FormalCandidateProgress")
        if identity.run_id != self.run.run_id:
            raise TeamConfigurationError("typed candidate run identity is stale")
        if identity.protocol_agent_id != protocol_id:
            raise TeamConfigurationError("typed candidate protocol identity drifts from progress")
        if identity.original_delivery_id != delivery_id:
            raise TeamConfigurationError("typed candidate delivery_id is foreign or stale")
        formal_contract = formal_run_contract_for(self.run.configuration)
        post_receipt_conflict = (
            response_kind == "conflict"
            and formal_contract is not None
            and formal_contract.requirement_id == "R2.3-003"
            and progress.state == "complete"
            and self._protocol_candidate_responses.get(delivery_id) == "receipt"
            and progress.post_receipt_revision_enabled
        )
        if (
            progress.state not in {"awaiting_receipt", "redrive_sent"}
            and not post_receipt_conflict
        ) or progress.paused:
            raise TeamConfigurationError("typed candidate is not awaiting a Protocol response")
        if progress.timeout_latched or progress.terminal_failure_latched:
            raise TeamConfigurationError("typed candidate progress is terminal")
        try:
            candidate_digest, semantic_digest = formal_candidate_digests(candidate)
        except FormalCandidateError as exc:
            raise TeamConfigurationError("retained formal candidate is invalid") from exc
        if (
            candidate_digest != identity.candidate_digest
            or semantic_digest != identity.semantic_digest
        ):
            raise TeamConfigurationError("retained formal candidate identity drifted")
        previous_response = self._protocol_candidate_responses.get(delivery_id)
        if previous_response == "conflict":
            raise TeamConfigurationError("typed candidate response was already built")
        if response_kind == "conflict" and previous_response != "receipt":
            raise TeamConfigurationError(
                "typed candidate conflict requires the canonical receipt first"
            )
        if previous_response == "receipt" and response_kind == "receipt":
            raise TeamConfigurationError("typed candidate response was already built")
        return deepcopy(candidate), identity

    def _build_protocol_candidate_receipt(
        self,
        protocol_id: str,
        delivery_id: str,
    ) -> dict[str, Any]:
        """Build an exact formal receipt from Runner-retained candidate state."""

        candidate, identity = self._active_protocol_candidate(
            protocol_id,
            delivery_id,
            response_kind="receipt",
        )
        formal_contract = formal_run_contract_for(self.run.configuration)
        if formal_contract is not None and formal_contract.requirement_id == "R2.3-003":
            try:
                validate_r23003_candidate_declarations(candidate)
            except ValueError as exc:
                raise TeamConfigurationError(str(exc)) from exc
        try:
            receipt = build_candidate_receipt(candidate)
        except ProtocolRetrievalFallbackError as exc:
            raise TeamConfigurationError(str(exc)) from exc
        try:
            normalized = validate_formal_receipt(
                receipt,
                candidate_revision=identity.candidate_revision,
                semantic_digest=identity.semantic_digest,
                candidate_digest=identity.candidate_digest,
            )
        except FormalCandidateError as exc:
            raise TeamConfigurationError("canonical candidate receipt does not match active identity") from exc
        self._protocol_candidate_responses[delivery_id] = "receipt"
        self._protocol_candidate_receipt_digests[delivery_id] = canonical_digest(normalized)
        return {
            "delivery_id": delivery_id,
            "candidate": candidate,
            "receipt": deepcopy(normalized),
            "receipt_json": self._canonical_bytes(normalized).decode("utf-8"),
        }

    def _build_protocol_candidate_conflict(
        self,
        protocol_id: str,
        delivery_id: str,
        conflict_code: str,
        conflict_detail: str,
    ) -> dict[str, Any]:
        """Build an exact formal conflict from Runner-retained candidate state."""

        candidate, identity = self._active_protocol_candidate(
            protocol_id,
            delivery_id,
            response_kind="conflict",
        )
        formal_contract = formal_run_contract_for(self.run.configuration)
        if formal_contract is not None and formal_contract.requirement_id == "R2.3-003":
            receipt_digest = self._protocol_candidate_receipt_digests.get(delivery_id)
            workspace_version = self._formal_workspace_version or self.run.scope.get(
                "workspace_version"
            )
            if not isinstance(receipt_digest, str) or not receipt_digest:
                raise TeamConfigurationError("typed candidate conflict has no accepted receipt digest")
            if not isinstance(workspace_version, str) or not workspace_version:
                raise TeamConfigurationError("typed candidate conflict has no workspace version")
            try:
                conflict = build_existing_scope_candidate_conflict(
                    candidate,
                    conflict_code,
                    conflict_detail,
                    original_delivery_id=identity.original_delivery_id,
                    receipt_digest=receipt_digest,
                    workspace_version=workspace_version,
                )
            except ProtocolRetrievalFallbackError as exc:
                raise TeamConfigurationError(str(exc)) from exc
        else:
            try:
                conflict = build_candidate_conflict(candidate, conflict_code, conflict_detail)
            except ProtocolRetrievalFallbackError as exc:
                raise TeamConfigurationError(str(exc)) from exc
        try:
            normalized = validate_formal_conflict(
                conflict,
                candidate_revision=identity.candidate_revision,
                semantic_digest=identity.semantic_digest,
                candidate_digest=identity.candidate_digest,
            )
        except FormalCandidateError as exc:
            raise TeamConfigurationError("canonical candidate conflict does not match active identity") from exc
        prior_response = self._protocol_candidate_responses.get(delivery_id)
        self._protocol_candidate_responses[delivery_id] = "conflict"
        if formal_contract is not None and formal_contract.requirement_id == "R2.3-003":
            if prior_response == "receipt" and self._modeling_context_gate is not None:
                self._modeling_context_gate.invalidate("post_receipt_context_drift")
            if self._candidate_platform_gate is not None:
                self._candidate_platform_gate.close("pre_mutation_binding_conflict")
        return {
            "delivery_id": delivery_id,
            "candidate": candidate,
            "conflict": deepcopy(normalized),
            "conflict_json": self._canonical_bytes(normalized).decode("utf-8"),
        }

    def _frozen_acceptance_question_ids(self) -> tuple[str, ...]:
        """Resolve the ordered standard-owned CQ IDs for Coordinator text."""

        if not self._formal_coordination_enabled() or self.run is None:
            return ()
        if self.acceptance is not None:
            ids = self.acceptance.frozen_question_ids()
        else:
            policy = self._acceptance_ticket_policy(self.run.configuration)
            ids = tuple(item["id"] for item in policy["competency_questions"])
        if not ids or len(set(ids)) != len(ids):
            raise TeamConfigurationError("formal acceptance must expose unique ordered question IDs")
        return ids

    def _task_text(self, role: str | None = None) -> str:
        assert self.run
        task = self.run.configuration.task
        if task.schema_version == 2:
            proof_gate = (
                getattr(self.run, "gate_binding", None) is not None
                or self._expected_matrix_binding(self.run.configuration) is not None
            )
            generation = (
                self.coordinator_phase.generation
                if self._formal_coordination_enabled() and self.coordinator_phase
                else None
            )
            formal_contract = formal_run_contract_for(self.run.configuration)
            is_r23003 = formal_contract is not None and formal_contract.requirement_id == "R2.3-003"
            formal_requirement_label = "R2.3-003" if is_r23003 else "R2.3-005"
            standard_policy = (
                self._acceptance_ticket_policy(self.run.configuration)
                if self._formal_coordination_enabled()
                else {}
            )
            question_count = int(standard_policy.get("question_count", 0) or 0)
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
                + "Use `mcp__team_transport__send_team_message` for direct Team Transport messages and call "
                + "`mcp__team_transport__report_task_result` exactly once before ending. "
                + "Protocol may use only its configured ontology-platform MCP tools."
            )
            if generation is not None:
                text += (
                    f"\nCurrent coordination generation: {generation}. "
                    "Include this non-secret generation unchanged in the role's fixed "
                    "`mcp__team_transport__send_coordination` call."
                )
            if role == "acceptance":
                report_projection = (
                    f"an ordered standard-owned set of {question_count} competency questions"
                    if is_r23003
                    else "exactly two terminal Examiner reports per round"
                )
                final_projection = (
                    "Only after the Runner-projected final question (is_final_question=true) has a current, usable PASS "
                    if is_r23003
                    else "Only after the final cq-002 usable PASS has been routed successfully "
                )
                live_round_instruction = (
                    "Acceptance remains live after every non-final PASS, and "
                    if is_r23003
                    else "Acceptance remains live after every non-final cq-001 PASS, and "
                )
                return (
                    task.objective
                    + (
                        f"\nCurrent coordination generation: {generation}. "
                        if generation is not None
                        else ""
                    )
                    + "\nYou are the persistent Acceptance role. The Runner supplies an immutable ticket, "
                    "a versioned standard, and "
                    + report_projection
                    + ". Do not "
                    "read staged source paths, call platform tools, spawn Agents, or use generic multi-agent "
                    "features. Use only the Runner-owned Acceptance capability to acknowledge the ticket, "
                    "retrieve child reports, and submit one canonical PASS/FAIL/BLOCKED verdict to Coordinator. "
                    "Wait for the Runner's acceptance-start delivery before calling acceptance_get_ticket or "
                    "reporting a missing-ticket issue; it carries the fixed acceptance_id and the exact "
                    "round_id (the ticket's acceptance_round_id) to use for this round. "
                    "For acceptance_child_start, provide only acceptance_id, round_id, kind, and a fresh "
                    "unique request_id. The Host derives every mechanical field: the kind-specific child "
                    "projection and its digest (from the immutable ticket), the ticket_digest (from the "
                    "round), and the attempt (Host-tracked per round/kind: 0 for the first start, 1 for the "
                    "single permitted identical-input retry). Omit input_ref and input_digest entirely (the "
                    "schema rejects them) and omit ticket_digest/attempt (the schema ignores them); never "
                    "construct, hash, or substitute any of these mechanical bindings. "
                    "For acceptance_child_recycle, completion_ref is exactly one of two one-key JSON objects: "
                    "{\"terminal_report_digest\":\"<report_digest>\"} or "
                    "{\"infrastructure_failure_digest\":\"<failure_digest>\"}. For an infrastructure failure, "
                    "copy only the inner readiness/failure-record failure_digest string into the outer "
                    "infrastructure_failure_digest key. Never send failure_digest as the outer key, never pass "
                    "the whole readiness/failure object, and never add type, ready, failure_category, "
                    "reason_code, attempt, or other fields. "
                    "Keep the Acceptance session alive across rounds; never send child terminal state through "
                    "Team Transport. Bind question, acceptance_round_id, slice revision, ticket digest, typed "
                    "evidence, and complete model-state identity in every verdict. Route only "
                    "acceptance_verdict_route to coordinator with the current generation and canonical "
                    "verdict JSON as text. "
                    + live_round_instruction
                    + "after any FAIL or BLOCKED verdict; do not call report_task_result for those outcomes. "
                    + final_projection
                    + "may you call Team "
                    "Transport report_task_result exactly once, using report_task_result(status=completed, ...) "
                    "with a concise summary "
                    "before ending. The ordinary acceptance_verdict_route delivery is not a terminal report "
                    "and cannot substitute for that completed Team Transport call."
                    )
            if role == "protocol":
                protocol_capability_operations: set[str] = set()
                if self.acceptance is not None:
                    descriptor = self.acceptance.capability_descriptors.get("protocol", {})
                    advertised = descriptor.get("operations", [])
                    if isinstance(advertised, list):
                        protocol_capability_operations = {
                            value for value in advertised if isinstance(value, str)
                        }
                typed_candidate_binding = {
                    "protocol_build_candidate_receipt",
                    "protocol_build_candidate_conflict",
                }.issubset(protocol_capability_operations)
                text += (
                    "\nProtocol startup barrier: wait for a direct Modeling Team Transport delivery containing the "
                    "complete candidate before making any ontology_platform MCP call. Do not call any "
                    "ontology_platform health, read, write, validation, reasoning, or retrieval tool before that "
                    "delivery is received and its candidate receipt is successfully built. This prohibition "
                    "explicitly includes `check_platform_health`, `get_project_build_context`, "
                    "`get_ontology_workspace_context`, and `get_modeling_context`; it also covers every other "
                    "configured ontology_platform tool. First build the receipt with the Runner-private "
                    "`protocol_build_candidate_receipt` capability when advertised, otherwise with the native "
                    "`protocol_mechanics`/`build_candidate_receipt` tool using the unchanged delivered candidate. "
                    "The `candidate_receipt_required` error means this barrier is still closed: stop and wait for "
                    "Modeling rather than retrying a health/read call. Use fully-qualified Team Transport MCP "
                    "names (`mcp__team_transport__send_team_message`, `mcp__team_transport__send_coordination`, "
                    "and `mcp__team_transport__report_task_result`) for all Team Transport calls. "
                    "\nYou must read the enumerated modeling-batch-item-contract.json source. "
                    "You must also read the enumerated acceptance-stage-handoff-contract.json source; it is the "
                    "authoritative nested schema for modeling_receipts, platform_read evidence_ref/page fields, "
                    "stage-specific successful statuses, and canonical handoff/delivery digest rules. Do not "
                    "guess nested receipt fields from this prompt or Python implementation. "
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
                    f" In the formal {formal_requirement_label} gate, first obtain the current candidate and mechanical receipt: use "
                    "the Runner-typed candidate receipt path when it is advertised below, otherwise call "
                    "build_candidate_receipt. This builder step does not send Team Transport. Complete the full "
                    "platform-translation decision before any response: if translation conflicts, call the "
                    "corresponding typed or native build_candidate_conflict path with a stable conflict_code and "
                    "concrete conflict_detail, then send only conflict_json; if translation succeeds, send only "
                    "receipt_json. Never hand-write a conflict or reuse prior-delivery digests. For every current "
                    "candidate or revision, send exactly one of those two responses through Team Transport, with "
                    "reply_to_delivery_id set to that candidate's delivery_id. Remain active for "
                    "revisions, and report terminal only after the Runner delivers Modeling's terminal-handoff. "
                    "Preserve source-grounded evidence_citations when present; do not read/guess source locators or "
                    "owner answers. Use the generic mechanics contract and configured retrieval fallback for ordinary "
                    "candidates. For ordinary formal retrieval, use the accepted candidate's consumer_query "
                    "required_paths as the sole plan: issue one query_semantic_context call per required path with "
                    "query exactly equal to that path, singleton relation/fact resource_types, asserted-only and "
                    "run-owned ontology scope; broad CQ/question queries and expected answers never count. The "
                    "host artifact gate validates each frozen cursor chain and registers the typed receipt. Emit only silent_for_acceptance to coordinator through "
                    "`mcp__team_transport__send_coordination` with the current generation after the ordered protocol work is quiet."
                )
                if is_r23003:
                    text += (
                        " Before invoking any Session, Lease, batch, validation, reasoning, or other stateful "
                        "ontology_platform tool after an accepted candidate receipt, call the exact-O "
                        "`get_modeling_context` read through the configured Protocol surface and verify the same "
                        "Project/Ontology, ready workspace, non-empty workspace_version, no issues, and no stale "
                        "derived state. An unequal workspace_version invalidates the old context and candidate "
                        "receipt; make the typed zero-mutation full-revision conflict path and wait for a complete "
                        "revised candidate before any mutation. Never reuse a stale receipt or send a patch."
                    )
                if self._formal_coordination_enabled() and self.acceptance is not None:
                    text += (
                        f" For the formal {formal_requirement_label} acceptance gate, the Runner has issued the exact non-secret "
                        f"stage-handoff nonce {self.acceptance.stage_handoff_nonce}. After all five current-run "
                        "stages (dry-run, apply, readback, validation, reasoning) and governed retrieval are "
                        "complete, send one canonical compact JSON object directly to Coordinator with "
                        "`mcp__team_transport__send_team_message` (not `mcp__team_transport__send_coordination`), using schema "
                        "r2-3-005-acceptance-stage-handoff/v1 and exact fields "
                        "schema_version,handoff_id,handoff_nonce,task_id,producer_run_id,slice_id,slice_revision, "
                        "model_state,model_state_digest,candidate_digest,modeling_receipts,handoff_digest. "
                        "The capability supplies the nonce, receipt bindings, and canonical digest; include no source "
                        "bytes, expected answers, or ticket fields. Call protocol_build_acceptance_stage_handoff with "
                        "exactly protocol_id=protocol and DO NOT supply stage_calls: the carrier auto-selects the "
                        "five canonical final-state observed calls (the final apply_atomic over the live workspace "
                        "version, its paired validated dry_run, the final get_modeling_context readback, and the "
                        "succeeded validation/reasoning over the live graph set). protocol_list_platform_artifacts "
                        "is for your awareness only; never hand-pick stages or compute receipts, pages, digests, or "
                        "artifact paths in model reasoning. "
                        "Send the returned handoff_json unchanged once. The "
                        "Runner rejects unobserved calls, wrong stage tool/mode/status/scope, artifact tamper, and "
                        "candidate identities other than the accepted candidate. Coordinator must pass the exact "
                        "delivery_id and unchanged object to its draft capability."
                    )
                if typed_candidate_binding:
                    text += (
                        " The Runner-private Protocol capability advertises typed formal candidate binding: "
                        "for every current Modeling candidate or candidate-redrive, call "
                        "protocol_build_candidate_receipt with exactly protocol_id=protocol and the original "
                        "delivery_id. Do not pass candidate JSON, candidate_text, path, digest, recipient, or "
                        "transport fields; the Runner resolves the retained exact candidate and returns structured "
                        "candidate plus receipt and exact canonical receipt_json; this obtains the retained data but "
                        "does not send it. Complete the translation decision before any Team Transport response. If "
                        "translation cannot proceed, call protocol_build_candidate_conflict with exactly the same "
                        "protocol_id and delivery_id plus stable conflict_code and concrete conflict_detail, then "
                        "send only its unchanged conflict_json with expects_reply=true. If translation succeeds, "
                        "send only the unchanged receipt_json with expects_reply=false. Every candidate or revision "
                        "gets exactly one of receipt_json or conflict_json, never both, with reply_to_delivery_id set "
                        "to the original delivery_id. The typed capability never sends Team Transport; it permits "
                        "one conflict immediately after that receipt build, before either response is sent, but "
                        "rejects duplicate receipt/conflict calls, stale or foreign IDs, and terminal delivery IDs."
                    )
                    if is_r23003:
                        text += (
                            " For R2.3-003 only, when an accepted receipt has already been sent and registered and a "
                            "later live binding read exposes a pre-mutation mismatch, call the typed conflict builder "
                            "with the original delivery_id, then send its unchanged conflict_json as a new standalone "
                            "Protocol-to-Modeling delivery with expects_reply=true and reply_to_delivery_id=None. The "
                            "typed conflict must retain original_delivery_id, receipt_digest, workspace_version, and "
                            "mutation_state=zero-mutation; Modeling replies with one full revised candidate bound to "
                            "this standalone conflict delivery_id. Pre-receipt conflicts and all R2.3-005 candidates keep "
                            "the original reply-bound semantics. "
                            " If protocol_build_candidate_receipt itself fails at the receipt gate (including the "
                            "R2.3-003 exact-delete validator), do not retry that call or send any accepted receipt. "
                            "Use the native protocol_mechanics build_candidate_conflict with the unchanged complete "
                            "candidate and a stable validator conflict code/detail. The native MCP result has only content "
                            "and structuredContent (no conflict_json): verify content[0].text parses to structuredContent "
                            "and equals its canonical JSON serialization (ensure_ascii=false, sorted keys, compact "
                            "separators), then send only content[0].text with expects_reply=true and "
                            "reply_to_delivery_id bound to the original candidate delivery. This is the reply-bound "
                            "request for Modeling to send one full revised candidate bound to the conflict delivery; "
                            "never send free text, a patch, or a duplicate receipt/reply. If the native conflict builder "
                            "or result-shape check fails, report blocked and send no receipt/reply."
                        )
                if proof_gate:
                    text += (
                        " For this proof-gated task, before the first submit_modeling_batch call, validate assertion "
                        "IDs/scope/citations against the frozen proof matrix, write the run-local "
                        "candidate-item-evidence-map, compare the group-projected safe dry-run Evidence plan, and "
                        "complete the native proof-v2 verifier."
                    )
                context = self.run.protocol_context
                if context:
                    return text + "\nMechanical platform scope (no credential): " + json.dumps(
                        context, ensure_ascii=False, sort_keys=True
                    )
            if role == "coordinator":
                typed_ticket_binding = False
                if self._formal_coordination_enabled() and self.acceptance is not None:
                    coordinator_descriptor = self.acceptance.capability_descriptors.get(
                        "coordinator", {}
                    )
                    advertised = coordinator_descriptor.get("operations", [])
                    typed_ticket_binding = (
                        isinstance(advertised, list)
                        and "coordinator_build_acceptance_ticket_draft_from_delivery" in advertised
                    )
                frozen_question_ids = self._frozen_acceptance_question_ids()
                frozen_question_instruction = ""
                if frozen_question_ids:
                    rendered_ids = ", ".join(f"`{question_id}`" for question_id in frozen_question_ids)
                    if is_r23003:
                        frozen_question_instruction = (
                            " Before any typed ticket draft, read the Runner-provided ordered standard list; "
                            f"the question IDs in order are {rendered_ids} (question_count={len(frozen_question_ids)}). "
                            "Use each ID once with a positive ticket_revision and use Runner-projected ordinal/count/"
                            "previous/next/is_final metadata. Never infer order or finality from an ID name."
                        )
                    else:
                        frozen_question_instruction = (
                            " Before any typed ticket draft, read the task's Runner-provided frozen-question list; "
                            f"the exact two IDs are {rendered_ids}. Use only these IDs, once each, with a positive "
                            "ticket_revision (revision 1 for the first draft). Never guess an abbreviated ID such as "
                            "`cq-1`, derive an ID from Protocol, or ask Protocol to provide the IDs. If the task does "
                            "not expose exactly these two IDs, do not call the draft capability."
                        )
                draft_revision_instruction = (
                    " The Runner projects ordinal/count/previous/next/is_final metadata for each ordered "
                    "standard question; use that metadata and never infer finality or order from an ID."
                    if is_r23003
                    else " Both frozen questions may use revision 1; do not treat the second question as a duplicate."
                )
                if typed_ticket_binding:
                    ticket_instruction = (
                        " When Protocol sends the structured acceptance-stage handoff, retain only the "
                        "original delivery_id from the direct Team Transport envelope and call the "
                        "Runner-private coordinator_build_acceptance_ticket_draft_from_delivery once "
                        "per frozen question, passing exactly coordinator_id=coordinator, "
                        "handoff_delivery_id, question_id, and positive ticket_revision. Do not parse, "
                        "copy, shorten, reconstruct, or resend handoff JSON; do not provide handoff_digest, "
                        "model_state, stage receipts, source paths, recipient, or transport fields. The "
                        "Runner resolves the exact registered Protocol delivery and owns nonce, current-run "
                        "stage receipts, authenticated live model state, canonical read allowlist, staged "
                        "source digests, and frozen policy."
                        + draft_revision_instruction
                        + " Publish only the complete returned draft "
                        "exactly once through coordinator_publish_acceptance_ticket."
                        + frozen_question_instruction
                    )
                else:
                    ticket_instruction = (
                        " When Protocol sends the structured acceptance-stage handoff, parse its exact JSON and "
                        "call the Runner-private coordinator_build_acceptance_ticket_draft once per question, "
                        "passing the delivery_id from the direct Team Transport envelope, the unchanged "
                        "handoff object and digest, the frozen question_id, and the positive ticket_revision. "
                        "The capability owns staged source digests, authenticated live model_state, canonical "
                        "read allowlist, standard fields, and all five receipt checks. Publish only the returned "
                        "complete draft exactly once through coordinator_publish_acceptance_ticket, passing the "
                        "same object/digest/requirement reference; never hand-author, shorten, replace, or mutate "
                        "it. `{}`/shorthand, changed run/project/ontology/state/slice/digest, or any second draft "
                        "is rejected."
                        + frozen_question_instruction
                    )
                sequential_instruction = ""
                if self._formal_coordination_enabled():
                    if is_r23003:
                        sequential_instruction = (
                            "\nFormal ordered N-CQ acceptance is mandatory: after each current question receives a usable PASS, "
                            "start exactly the Runner-projected next_question_id only after the prior round's children are "
                            "reclaimed. A question with is_final_question=true starts no further round and waits for normal "
                            "settlement. FAIL/BLOCKED never advances, and rounds never overlap."
                        )
                    else:
                        sequential_instruction = (
                            "\nFormal R2.3-005 sequential acceptance is mandatory: after you receive and confirm the "
                            "cq-001 PASS verdict through the Runner-private verdict capability, immediately send "
                            "exactly one acceptance_start for the already published cq-002 ticket, using that "
                            "ticket's exact acceptance_round_id. Do not wait for a cq-002 verdict before starting "
                            "cq-002; no such verdict can exist until its round is started. Do not rebuild, mutate, "
                            "or republish either ticket while advancing. A final cq-002 PASS starts no further "
                            "round and waits for the normal Acceptance terminal handoff and settlement. FAIL returns "
                            "to the existing Modeling repair/revision path; BLOCKED waits for recovery or revision; "
                            "neither non-PASS verdict advances to the next CQ, and never overlap two rounds."
                        )
                return text + (
                    "\nCoordinator receives no raw business or consumer-source bytes. Use only the "
                    "Runner-private capability MCP to publish the fixed requirement-owned ticket and "
                    "read the Acceptance verdict; do not redefine CQs, approved-source paths, or the "
                    "quality standard. After Modeling-ready and Protocol-silent, emit only "
                    "acceptance_start to acceptance through `mcp__team_transport__send_coordination` with the current "
                    "generation and acceptance_round_id as text. Use only the Project/Ontology created for this "
                    "run; never reuse or bind a prior/caller-supplied scope and never initiate a second semantic "
                    "start."
                    + ticket_instruction
                    + " Only after unchanged publication succeeds "
                    "send acceptance_start with the returned acceptance_round_id. Coordinator never reads staged "
                    "business sources or receipt payload bytes."
                    + sequential_instruction
                    + "\nWhen forwarding an outer answer to a grounded Modeling question, send that exact answer "
                    "once with reply_to_delivery_id set to the current Modeling question delivery_id. Do not "
                    "duplicate it or leave it unbound."
                    "\n`mcp__team_transport__report_task_result` is recorded exactly once only after Modeling, Protocol, and Acceptance "
                    "have each reported completed or blocked. A dependency rejection is not recorded; wait for "
                    "their terminal handoffs and retry without reviewing their semantics. Coordinator reports last."
                )
            if role == "modeling":
                modeling_text = text + (
                    "\nEmit only ready_for_acceptance to coordinator through `mcp__team_transport__send_coordination` with "
                    "the current generation once the semantic slice is ready; never emit "
                    "silent_for_acceptance or acceptance_start."
                    "\nSend each platform-neutral candidate or revision with expects_reply=true and retain the "
                    "returned delivery_id. Wait for Protocol's delivered receipt or conflict whose "
                    "reply_to_delivery_id matches it. On conflict, send a revision as a new expects_reply request; "
                    "if you cannot revise, send no further candidate and report blocked. Without an established "
                    "reply request, Modeling may report only blocked, never completed. Every candidate item must "
                    "preserve source-grounded evidence_citations when available; do not put platform IDs, Batch IDs, "
                    "or receipt labels into the platform-neutral candidate."
                )
                if is_r23003:
                    modeling_text += (
                        "\nR2.3-003 Modeling has one independent project-scoped read key and exactly three "
                        "read tools through the local `modeling_read_proxy`: `get_modeling_context`, "
                        "`get_ontology_read_model`, and `query_semantic_context`. Use the exact Project/Ontology "
                        "scope supplied by the proxy; read only model_name classes, entities, facts, or rules, "
                        "and use ontologies scope with ontology_ids containing exactly this ontology. Do not call "
                        "history/delta, writes, validation, reasoning, or any other platform tool. First call "
                        "`get_modeling_context` and require a ready workspace, non-empty workspace_version, "
                        "non-negative resource counts, no issues, and no stale derived state. The Runner keeps an "
                        "immutable context receipt; direct candidate Transport and the staged candidate capability "
                        "remain closed until that exact context call succeeds. After a receipt or before any later "
                        "Protocol stateful action, re-read the exact context; a workspace-version drift is a typed "
                        "zero-mutation conflict requiring one complete revised candidate, never a patch or stale receipt."
                    )
                if self._candidate_publication is not None:
                    identity = self._candidate_publication.identity
                    modeling_text += (
                        "\nThis run has one Runner-validated continuation candidate, revision "
                        f"{identity.candidate_revision}, candidate_digest {identity.candidate_digest}, and "
                        f"semantic_digest {identity.semantic_digest}. Reuse it only by calling the "
                        "Runner-private modeling_publish_staged_candidate capability exactly once with "
                        "modeling_id=modeling. Do not read or parse a carrier, invoke a shell or interpreter, "
                        "serialize JSON, send the outer continuation envelope, or call `mcp__team_transport__send_team_message` for this "
                        "candidate. The capability owns the exact candidate_text, digest checks, recipient, "
                        "expects_reply flag, and delivery ID. Retain its returned delivery_id and wait for the "
                        "normal Protocol reply bound to that ID."
                    )
                if proof_gate:
                    modeling_text += (
                        " For this proof-gated task, every item must carry non-empty evidence_citations with the "
                        "exact document_name, excerpt, source artifact/locator/hash, and owner_answer_id fields, "
                        "and the candidate must satisfy the frozen assertion matrix."
                    )
                return modeling_text
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
        elif action == "issue_resolution":
            if not self._formal_coordination_enabled() or self.transport is None:
                raise TeamConfigurationError("issue escalation capability is unavailable")
            resolution = self._outer_issue_resolution(message)
            try:
                self.transport.persist_issue_resolution(resolution)
            except RoutingError as exc:
                raise TeamConfigurationError(str(exc)) from exc
            # Persist first; only then make the resolution visible to Coordinator.
            self._append_evidence("issue-resolution", resolution.as_dict())
            coordinator = self._issue_coordinator_id()
            try:
                self.adapter.send_message(
                    coordinator,
                    RuntimeDelivery(
                        sender_id="user/outer",
                        recipient_id=coordinator,
                        kind="issue-resolution",
                        text=json.dumps(resolution.as_dict(), ensure_ascii=False, sort_keys=True),
                    ),
                )
            except Exception as exc:
                raise TeamConfigurationError("issue resolution Coordinator delivery failed") from exc
        elif action == "user":
            if self._formal_coordination_enabled() and set(message) - {
                "action",
                "text",
                "question_delivery_id",
            }:
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
                    if "question_delivery_id" in message:
                        # An explicit ID is a mechanical disambiguator only.  The
                        # release path below remains the authority for displayed,
                        # unconsumed, same-run/project and origin bindings.
                        question_delivery_id = message["question_delivery_id"]
                    else:
                        # Preserve the text-only compatibility path when exactly
                        # one currently displayed question is eligible.
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

    def _outer_issue_resolution(self, message: dict[str, Any]) -> IssueResolution:
        """Parse one strict outer resolution envelope; no opaque JSON payloads."""
        base = {"action", "issue_id", "reporter_id", "control_epoch", "resolution_type"}
        if set(message) - {
            *base,
            "resolution_text",
            "repair_component",
            "before_digest",
            "after_digest",
            "verification_reference",
            "mutation_reconciliation",
        }:
            raise TeamConfigurationError("issue resolution envelope has invalid fields")
        if not base.issubset(message):
            raise TeamConfigurationError("issue resolution envelope is incomplete")
        resolution_type = message.get("resolution_type")
        if resolution_type in {"guidance", "abort"}:
            expected = base | {"resolution_text"}
            if set(message) != expected:
                raise TeamConfigurationError("issue resolution guidance fields are invalid")
        elif resolution_type == "repair_completed":
            expected = base | {
                "repair_component",
                "before_digest",
                "after_digest",
                "verification_reference",
                "mutation_reconciliation",
            }
            if set(message) != expected:
                raise TeamConfigurationError("issue resolution repair fields are invalid")
        else:
            raise TeamConfigurationError("issue resolution type is invalid")
        try:
            return IssueResolution(
                run_id=self.run.run_id if self.run else "",
                issue_id=message["issue_id"],
                reporter_id=message["reporter_id"],
                resolution_type=resolution_type,
                control_epoch=message["control_epoch"],
                resolution_text=message.get("resolution_text"),
                repair_component=message.get("repair_component"),
                before_digest=message.get("before_digest"),
                after_digest=message.get("after_digest"),
                verification_reference=message.get("verification_reference"),
                mutation_reconciliation=message.get("mutation_reconciliation"),
            )
        except (TypeError, IssueError) as exc:
            raise TeamConfigurationError("issue resolution envelope is invalid") from exc

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
                or existing.get("sequence") != delivery.sequence
                or existing.get("timestamp") != delivery.timestamp
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
            "sequence": delivery.sequence,
            "timestamp": delivery.timestamp,
            "origin_agent_id": modeling,
            "displayed": False,
            "consumed": False,
        }

    def _formal_candidate_roles(self) -> tuple[str, str] | None:
        if not self._formal_coordination_enabled() or not self.run:
            return None
        role_ids = {
            agent.package.role: agent.agent_id
            for agent in self.run.configuration.profile.agents
        }
        modeling, protocol = role_ids.get("modeling"), role_ids.get("protocol")
        # Small owner-answer/foreground fixtures from the pre-candidate formal
        # gate intentionally contain only Modeling+Coordinator.  They must keep
        # their existing display semantics; the production profile is validated
        # with all four roles before this gate is enabled.
        if not isinstance(modeling, str) or not isinstance(protocol, str):
            return None
        return modeling, protocol

    def _formal_protocol_thread_id(self, protocol_agent_id: str) -> str:
        agents = getattr(self.adapter, "agents", None)
        agent = agents.get(protocol_agent_id) if isinstance(agents, dict) else None
        thread_id = getattr(agent, "thread_id", None)
        if isinstance(thread_id, str) and thread_id:
            return thread_id
        # A fake/legacy adapter may not expose its private Codex thread.  The
        # fallback remains a stable pending identity while the real Codex path
        # always supplies its concrete thread id.
        return f"runtime-agent:{protocol_agent_id}"

    def _notify_candidate_receipt_registered(
        self,
        identity: Any,
        accepted_receipt_delivery_id: Any,
    ) -> None:
        """Wake the same Protocol Runtime thread once after the gate opens."""

        progress = self._candidate_progress
        gate = self._candidate_platform_gate
        if (
            gate is None
            or progress is None
            or self._formal_failure_latched
            or progress.paused
            or progress.timeout_latched
            or progress.terminal_failure_latched
        ):
            return
        if not isinstance(accepted_receipt_delivery_id, str) or not accepted_receipt_delivery_id:
            gate.close("receipt_notification_failed")
            self._append_evidence(
                "formal-candidate-progress",
                {
                    "event": "candidate-receipt-notification-failed",
                    "classification": "platform-contract",
                    "reason_code": "accepted-receipt-delivery-id-missing",
                },
            )
            self._latch_formal_candidate_failure(
                "platform-contract", "candidate-receipt-wakeup-delivery-id-missing"
            )
            raise TeamConfigurationError("candidate receipt registration wakeup failed")
        original_delivery_id = getattr(identity, "original_delivery_id", None)
        wakeup_key = (accepted_receipt_delivery_id, original_delivery_id)
        if wakeup_key in self._candidate_receipt_wakeup_sent:
            return
        try:
            notice = candidate_receipt_registered_notice(
                identity.__dict__ if hasattr(identity, "__dict__") else identity,
                accepted_receipt_delivery_id,
            )
        except CandidatePlatformGateError as exc:
            gate.close("receipt_notification_failed")
            self._append_evidence(
                "formal-candidate-progress",
                {
                    "event": "candidate-receipt-notification-failed",
                    "classification": "platform-contract",
                    "reason_code": "candidate-receipt-notice-invalid",
                },
            )
            self._latch_formal_candidate_failure(
                "platform-contract", "candidate-receipt-wakeup-notice-invalid"
            )
            raise TeamConfigurationError("candidate receipt registration wakeup failed") from exc
        self._candidate_receipt_wakeup_sent.add(wakeup_key)
        delivery = RuntimeDelivery(
            sender_id="runner/candidate-gate",
            recipient_id=identity.protocol_agent_id,
            kind=CANDIDATE_RECEIPT_REGISTERED_KIND,
            text=json.dumps(notice, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            delivery_id=f"candidate-receipt-registered:{accepted_receipt_delivery_id}",
            expects_reply=False,
            reply_to_delivery_id=accepted_receipt_delivery_id,
        )
        try:
            receipt = self.adapter.send_message(identity.protocol_agent_id, delivery)
        except Exception as exc:
            gate.close("receipt_notification_failed")
            self._append_evidence(
                "formal-candidate-progress",
                {
                    "event": "candidate-receipt-notification-failed",
                    "classification": "runtime/infrastructure",
                    "reason_code": "candidate-receipt-wakeup-dispatch-failed",
                },
            )
            self._latch_formal_candidate_failure(
                "runtime/infrastructure", "candidate-receipt-wakeup-dispatch-failed"
            )
            raise TeamConfigurationError("candidate receipt registration wakeup failed") from exc
        if not isinstance(getattr(receipt, "turn_id", None), str) or not receipt.turn_id:
            gate.close("receipt_notification_failed")
            self._append_evidence(
                "formal-candidate-progress",
                {
                    "event": "candidate-receipt-notification-failed",
                    "classification": "platform-contract",
                    "reason_code": "candidate-receipt-wakeup-turn-binding-missing",
                },
            )
            self._latch_formal_candidate_failure(
                "platform-contract", "candidate-receipt-wakeup-turn-binding-missing"
            )
            raise TeamConfigurationError("candidate receipt registration wakeup failed")
        self._append_evidence(
            "formal-candidate-progress",
            {
                "event": "candidate-receipt-registered",
                "run_id": notice["run_id"],
                "original_delivery_id": notice["original_delivery_id"],
                "accepted_receipt_delivery_id": notice["accepted_receipt_delivery_id"],
                "candidate_digest": notice["candidate_digest"],
                "dispatch_mode": getattr(receipt, "mode", None),
                "turn_id": receipt.turn_id,
            },
        )

    def _observe_formal_candidate_delivery(self, delivery: Any) -> str | None:
        roles = self._formal_candidate_roles()
        if roles is None or self._candidate_progress is None or not self.run:
            return None
        modeling, protocol = roles
        try:
            result = self._candidate_progress.observe_delivery(
                delivery,
                modeling_agent_id=modeling,
                protocol_agent_id=protocol,
                run_id=self.run.run_id,
                protocol_thread_id=self._formal_protocol_thread_id(protocol),
            )
        except FormalCandidateError:
            # Keep the failure at the modeling-quality/protocol boundary.  The
            # outer loop records terminal evidence and performs one cleanup;
            # pending state is never silently advanced on malformed envelopes.
            raise
        if result is not None:
            identity = self._candidate_progress.identity
            if (
                result in {"candidate", "revision"}
                and identity is not None
                and self._modeling_context_gate is not None
            ):
                self._modeling_context_gate.bind_candidate(
                    str(getattr(delivery, "delivery_id", "")), identity.candidate_digest
                )
            if result == "accepted" and identity is not None and self.acceptance is not None:
                self.acceptance.register_accepted_candidate(
                    candidate_revision=identity.candidate_revision,
                    candidate_digest=identity.candidate_digest,
                    candidate=self._candidate_progress.candidate,
                )
            if self._candidate_platform_gate is not None:
                if result in {"candidate", "revision", "conflict"}:
                    self._candidate_platform_gate.close(
                        "candidate_pending_receipt"
                        if result in {"candidate", "revision"}
                        else "protocol_conflict",
                    )
                elif result == "accepted" and identity is not None:
                    if self._candidate_progress.paused or self._formal_failure_latched:
                        self._candidate_platform_gate.close("receipt_notification_suppressed")
                    else:
                        gate_identity = dict(identity.__dict__)
                        if self._is_r23003_modeling_run():
                            context_gate = self._modeling_context_gate
                            context_receipt = context_gate.receipt if context_gate is not None else None
                            if context_gate is None or context_receipt is None:
                                self._candidate_platform_gate.close(
                                    "modeling_context_receipt_missing"
                                )
                                raise TeamConfigurationError(
                                    "R2.3-003 candidate receipt lacks the Modeling context binding"
                                )
                            gate_identity["modeling_context"] = {
                                "project_id": context_gate.project_id,
                                "ontology_id": context_gate.ontology_id,
                                "workspace_version": context_receipt.workspace_version,
                                "context_receipt_digest": context_receipt.receipt_digest,
                                "response_digest": context_receipt.response_digest,
                                "call_receipt_digest": context_receipt.call_receipt_digest,
                            }
                        self._candidate_platform_gate.open(gate_identity)
                        self._notify_candidate_receipt_registered(
                            identity,
                            getattr(delivery, "delivery_id", None),
                        )
            self._append_evidence(
                "formal-candidate-progress",
                {
                    "event": result,
                    "state": self._candidate_progress.state,
                    "delivery_id": getattr(delivery, "delivery_id", None),
                    "original_delivery_id": identity.original_delivery_id if identity else None,
                    "candidate_revision": identity.candidate_revision if identity else None,
                    "candidate_digest": identity.candidate_digest if identity else None,
                    "semantic_digest": identity.semantic_digest if identity else None,
                },
            )
        return result

    def _register_stage_handoff_delivery_if_exact(self, delivery: Any) -> dict[str, str] | None:
        """Register only the exact Runner-built Prompt-E delivery, if present."""

        if not self._formal_coordination_enabled() or self.acceptance is None:
            return None
        role_ids = self._formal_coordination_role_ids()
        is_handoff_channel = (
            delivery.sender_id == role_ids["protocol"]
            and delivery.recipient_id == role_ids["coordinator"]
        )
        # Primary path: Protocol relays the opaque builder token (the
        # handoff_id) as delivery text.  The Runner pre-bound the handoff at
        # build time, so recording does not depend on the Agent re-serializing
        # the nested handoff JSON -- a short token cannot be mangled the way
        # ~7 KB of nested JSON can.
        if is_handoff_channel:
            token_record = self.acceptance.register_stage_handoff_delivery_by_token(
                delivery_id=delivery.delivery_id,
                text=delivery.text,
                sender_role="protocol",
                recipient_role="coordinator",
            )
            if token_record is not None:
                self._append_evidence("acceptance-stage-handoff", token_record)
                return token_record
        # Backward-compatible path: a full unchanged handoff JSON text still
        # classifies by canonical bytes.  This keeps older sends and the exact
        # "builder output was mutated" guard available when no token is relayed.
        try:
            is_builder_output = self.acceptance.classify_stage_handoff_delivery(delivery.text)
        except AcceptanceContractError as exc:
            raise TeamConfigurationError(str(exc)) from exc
        if not is_builder_output:
            return None
        if not is_handoff_channel:
            raise TeamConfigurationError("stage handoff delivery role binding is invalid")
        handoff_record = self.acceptance.register_stage_handoff_delivery(
            delivery_id=delivery.delivery_id,
            text=delivery.text,
            sender_role="protocol",
            recipient_role="coordinator",
        )
        self._append_evidence("acceptance-stage-handoff", handoff_record)
        return handoff_record

    def _latch_formal_candidate_failure(self, classification: str, reason: str) -> None:
        """Record one terminal failure before the foreground performs cleanup."""

        if self._formal_failure_latched:
            return
        self._formal_failure_latched = True
        if self._candidate_progress is not None:
            self._candidate_progress.mark_terminal_failure()
        if self._candidate_platform_gate is not None:
            self._candidate_platform_gate.close("formal_candidate_terminal_failure")
        self._state(
            "TERMINAL_FAILURE_PENDING_CLEANUP",
            failure_category=classification,
            reason_code=reason,
        )
        self._append_evidence(
            "formal-candidate-terminal-failure",
            {
                "classification": classification,
                "complete_modeling_quality_result": False,
                "reason_code": reason,
                "cleanup_required": True,
            },
        )
        self.record_terminal_failure(classification, False)

    def _check_formal_candidate_progress(self) -> None:
        roles = self._formal_candidate_roles()
        if roles is None or self._candidate_progress is None:
            return
        issue_ledger = self._issue_ledger()
        if issue_ledger is not None and issue_ledger.pending:
            return
        self._candidate_progress.check_deadline(now=self.monotonic_clock())

    def _maybe_redrive_formal_candidate(self) -> None:
        roles = self._formal_candidate_roles()
        if roles is None or self._candidate_progress is None:
            return
        issue_ledger = self._issue_ledger()
        if issue_ledger is not None and issue_ledger.pending:
            return
        _, protocol = roles
        if not self._candidate_progress.redrive_ready(now=self.monotonic_clock()):
            return
        attribution = self._candidate_progress.original_runtime_attribution
        if attribution is None:
            raise FormalCandidateError("formal candidate redrive has no original Runtime attribution")
        delivery = RuntimeDelivery(
            sender_id=attribution.sender_id,
            recipient_id=attribution.recipient_id,
            kind="candidate-redrive",
            text=attribution.text,
            delivery_id=attribution.delivery_id,
            expects_reply=attribution.expects_reply,
            reply_to_delivery_id=attribution.reply_to_delivery_id,
        )
        receipt = self.adapter.send_message(protocol, delivery)
        self._candidate_progress.mark_redrive_dispatch(
            receipt, now=self.monotonic_clock()
        )
        self._append_evidence(
            "formal-candidate-progress",
            {
                "event": "redrive_sent",
                "recipient_id": protocol,
                "state": self._candidate_progress.state,
                "dispatch_mode": getattr(receipt, "mode", None),
                "turn_id": getattr(receipt, "turn_id", None),
                "redrive_count": 1,
            },
        )

    def _issue_coordinator_id(self) -> str:
        if not self.run:
            raise TeamConfigurationError("issue Coordinator is unavailable")
        for agent in self.run.configuration.profile.agents:
            if agent.package.role == "coordinator":
                return agent.agent_id
        raise TeamConfigurationError("issue Coordinator is unavailable")

    def _issue_ledger(self) -> Any | None:
        return getattr(self.transport, "issue_ledger", None)

    def _issue_control_from_payload(self, value: Any) -> IssueControl:
        if not isinstance(value, dict):
            raise TeamConfigurationError("issue control payload is invalid")
        resolution_value = value.get("resolution")
        resolution: IssueResolution | None = None
        if resolution_value is not None:
            if not isinstance(resolution_value, dict):
                raise TeamConfigurationError("issue control resolution is invalid")
            try:
                resolution = IssueResolution(**resolution_value)
            except (TypeError, IssueError) as exc:
                raise TeamConfigurationError("issue control resolution is invalid") from exc
        try:
            return IssueControl(
                run_id=value.get("run_id"),
                issue_id=value.get("issue_id"),
                coordinator_id=value.get("coordinator_id"),
                reporter_id=value.get("reporter_id"),
                action=value.get("action"),
                control_epoch=value.get("control_epoch"),
                resolution=resolution,
                reason=value.get("reason"),
            )
        except (TypeError, IssueError) as exc:
            raise TeamConfigurationError("issue control payload is invalid") from exc

    def _handle_issue_events(self, output: list[dict[str, Any]]) -> None:
        """Process Broker issue callbacks in the Runner main loop only."""
        if not self.transport or not self.transport.issue_escalation_enabled or not self.run:
            return
        with self._issue_event_lock:
            events, self._issue_event_queue = self._issue_event_queue[:], []
        if not events:
            return
        coordinator = self._issue_coordinator_id()
        for event in events:
            kind = event.get("kind") if isinstance(event, dict) else None
            if kind == "issue_report":
                issue = event.get("issue")
                if not isinstance(issue, dict):
                    raise TeamConfigurationError("issue report callback payload is invalid")
                issue_id = issue.get("issue_id")
                reporter_id = issue.get("reporter_id")
                if isinstance(issue_id, str) and isinstance(reporter_id, str):
                    identity = self._candidate_progress.identity if self._candidate_progress else None
                    candidate_identity = identity.__dict__.copy() if identity is not None else None
                    thread_id = self._formal_protocol_thread_id(reporter_id)
                    try:
                        issue = self.transport.bind_issue_context(
                            issue_id=issue_id,
                            reporter_id=reporter_id,
                            thread_id=thread_id,
                            candidate_identity=candidate_identity,
                        )
                    except RoutingError as exc:
                        raise TeamConfigurationError("issue context binding failed") from exc
                self._append_evidence("issue-report", issue)
                try:
                    self.adapter.send_message(
                        coordinator,
                        RuntimeDelivery(
                            sender_id="runner/issue",
                            recipient_id=coordinator,
                            kind="issue",
                            text=json.dumps(issue, ensure_ascii=False, sort_keys=True),
                        ),
                    )
                except Exception as exc:
                    issue_id = issue.get("issue_id")
                    reporter_id = issue.get("reporter_id")
                    if isinstance(issue_id, str) and isinstance(reporter_id, str):
                        try:
                            self.transport.fail_issue_rebind(
                                issue_id=issue_id,
                                reporter_id=reporter_id,
                                reason="Coordinator delivery failed",
                            )
                        except RoutingError:
                            pass
                    raise TeamConfigurationError("issue Coordinator delivery failed") from exc
                if self._candidate_progress is not None:
                    self._candidate_progress.pause(now=self.monotonic_clock())
                self._state(
                    "WAITING_REPAIR"
                    if issue.get("category") == "platform_repair"
                    else "WAITING_OWNER",
                    issue_id=issue.get("issue_id"),
                )
                self._append_evidence(
                    "issue-pause",
                    {
                        "issue_id": issue.get("issue_id"),
                        "reporter_id": issue.get("reporter_id"),
                        "state": "reported",
                        "candidate_paused": self._candidate_progress is not None,
                    },
                )
                continue
            if kind != "issue_control":
                raise TeamConfigurationError("unknown issue callback event")
            control = self._issue_control_from_payload(event.get("control"))
            self._dispatch_issue_control(control, output)

    def _dispatch_issue_control(self, control: IssueControl, output: list[dict[str, Any]]) -> None:
        if not self.transport or not self.run:
            raise TeamConfigurationError("issue transport is unavailable")
        if control.run_id != self.run.run_id or control.coordinator_id != self._issue_coordinator_id():
            raise TeamConfigurationError("issue control run binding is invalid")
        active_issue = self._issue_ledger().active_issue if self._issue_ledger() is not None else None
        if active_issue is None or active_issue.issue_id != control.issue_id:
            raise TeamConfigurationError("issue control issue binding is invalid")
        if control.action == "abort":
            self._issue_abort_requested = True
            self._append_evidence("issue-abort", control.as_dict())
            self._state("ABORTING", issue_id=control.issue_id)
            # Abort is explicit and terminal; no Runtime interrupt is used.
            return
        agent = getattr(self.adapter, "agents", {}).get(control.reporter_id)
        if agent is not None:
            process = getattr(agent, "process", None)
            if process is not None and callable(getattr(process, "poll", None)):
                try:
                    if process.poll() is not None:
                        self.transport.fail_issue_rebind(
                            issue_id=control.issue_id,
                            reporter_id=control.reporter_id,
                            reason="reporter App Server is dead",
                        )
                        raise TeamConfigurationError("issue reporter App Server is dead")
                except (IssueError, RoutingError) as exc:
                    raise TeamConfigurationError("issue reporter cannot be rebound") from exc
        if control.action == "resume" and control.resolution is not None:
            if control.resolution.resolution_type == "repair_completed":
                component = control.resolution.repair_component
                if component not in {"shared_backend_service", "shared_backend_data"}:
                    self.transport.fail_issue_rebind(
                        issue_id=control.issue_id,
                        reporter_id=control.reporter_id,
                        reason="repair component requires rebind",
                    )
                    raise TeamConfigurationError("issue repair requires rebind")
        before_thread = self._formal_protocol_thread_id(control.reporter_id)
        if active_issue.thread_id is not None and active_issue.thread_id != before_thread:
            self.transport.fail_issue_rebind(
                issue_id=control.issue_id,
                reporter_id=control.reporter_id,
                reason="issue control thread binding drift",
            )
            raise TeamConfigurationError("issue control thread binding drift")
        current_identity = self._candidate_progress.identity if self._candidate_progress else None
        current_candidate = current_identity.__dict__.copy() if current_identity is not None else None
        if active_issue.candidate_identity != current_candidate:
            self.transport.fail_issue_rebind(
                issue_id=control.issue_id,
                reporter_id=control.reporter_id,
                reason="issue control candidate binding drift",
            )
            raise TeamConfigurationError("issue control candidate binding drift")
        before_turn = getattr(agent, "active_turn_id", None) if agent is not None else None
        if control.action == "resume" and before_turn is not None:
            self.transport.fail_issue_rebind(
                issue_id=control.issue_id,
                reporter_id=control.reporter_id,
                reason="reporter did not finish its paused turn",
            )
            raise TeamConfigurationError("issue resume requires an idle reporter")
        try:
            receipt = self.adapter.send_message(
                control.reporter_id,
                RuntimeDelivery(
                    sender_id="runner/issue-control",
                    recipient_id=control.reporter_id,
                    kind="issue-control",
                    text=json.dumps(control.as_dict(), ensure_ascii=False, sort_keys=True),
                ),
            )
        except Exception as exc:
            self.transport.fail_issue_rebind(
                issue_id=control.issue_id,
                reporter_id=control.reporter_id,
                reason="issue control Runtime delivery failed",
            )
            raise TeamConfigurationError("issue control Runtime delivery failed") from exc
        after_thread = self._formal_protocol_thread_id(control.reporter_id)
        after_turn = getattr(agent, "active_turn_id", None) if agent is not None else getattr(receipt, "turn_id", None)
        if control.action == "resume" and getattr(receipt, "mode", None) != "start":
            self.transport.fail_issue_rebind(
                issue_id=control.issue_id,
                reporter_id=control.reporter_id,
                reason="resume did not start a new turn",
            )
            raise TeamConfigurationError("issue resume did not start a new turn")
        if before_thread != after_thread:
            self.transport.fail_issue_rebind(
                issue_id=control.issue_id,
                reporter_id=control.reporter_id,
                reason="issue control thread binding changed",
            )
            raise TeamConfigurationError("issue control thread binding changed")
        try:
            self.transport.mark_issue_dispatch(control)
        except RoutingError as exc:
            raise TeamConfigurationError("issue control CAS dispatch rejected") from exc
        if control.action == "pause":
            if self._candidate_progress is not None:
                self._candidate_progress.pause(now=self.monotonic_clock())
            self._state(
                "WAITING_REPAIR"
                if self._issue_ledger()
                and self._issue_ledger().active_issue
                and self._issue_ledger().active_issue.category == "platform_repair"
                else "WAITING_OWNER",
                issue_id=control.issue_id,
            )
            # Surface the issue only after Coordinator has reviewed it and
            # issued the bound cooperative pause. This is the structured
            # Coordinator-to-outer escalation boundary.
            output.append(
                {
                    "type": "issue",
                    "issue": active_issue.as_dict(state=self._issue_ledger().state),
                }
            )
        elif control.action == "resume":
            if self._candidate_progress is not None:
                self._candidate_progress.resume(now=self.monotonic_clock())
            self._state("RUNNING", issue_id=control.issue_id)
        self._append_evidence(
            "issue-control",
            {
                "issue_id": control.issue_id,
                "reporter_id": control.reporter_id,
                "action": control.action,
                "control_epoch": control.control_epoch,
                "before_thread_id": before_thread,
                "after_thread_id": after_thread,
                "before_turn_id": before_turn,
                "after_turn_id": after_turn,
                "turn_id": getattr(receipt, "turn_id", None),
                "dispatch_mode": getattr(receipt, "mode", None),
            },
        )
        output.append({"type": "issue-control", **control.as_dict()})

    def _observe_coordinator_message(self, message: Any) -> None:
        """Retain the coordinator hook without making prose a display authority.

        Formal outer-question display is bound only by
        :meth:`observe_foreground_output`, after the host successfully emits the
        exact Runner delivery envelope.  Coordinator text can be a paraphrase,
        can omit the question, or can contain unrelated text; none of those
        cases may change the pending question state.
        """
        del message

    def observe_foreground_output(self, output: list[dict[str, Any]]) -> None:
        """Bind formal outer questions to exact, successfully emitted envelopes.

        The foreground event loop calls this method only after ``emit`` returns.
        Validation is intentionally completed for the entire batch before any
        outer-question evidence is appended or any record is marked displayed.
        """
        if not self._formal_coordination_enabled() or not self.run:
            return
        if not isinstance(output, list):
            raise TeamConfigurationError("foreground output must be a list")

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
        project_id = self._project_binding()
        if not isinstance(project_id, str) or not project_id:
            raise TeamConfigurationError("outer question project binding is missing")

        expected_fields = {
            "type",
            "sequence",
            "sender_id",
            "recipient_id",
            "text",
            "timestamp",
            "delivery_id",
            "expects_reply",
            "reply_to_delivery_id",
        }
        records_to_display: list[dict[str, Any]] = []
        seen: set[str] = set()
        for envelope in output:
            if not isinstance(envelope, dict):
                raise TeamConfigurationError("foreground output envelope is invalid")
            delivery_id = envelope.get("delivery_id")
            if not isinstance(delivery_id, str):
                continue
            record = self._outer_questions.get(delivery_id)
            if record is None:
                # Ordinary peer/owner deliveries and terminal envelopes have
                # unrelated IDs.  They are not candidates for formal display.
                continue
            if set(envelope) != expected_fields:
                raise TeamConfigurationError("outer question display envelope fields drift")
            if (
                envelope.get("type") != "delivery"
                or not isinstance(envelope.get("sequence"), int)
                or isinstance(envelope.get("sequence"), bool)
                or not isinstance(envelope.get("timestamp"), (int, float))
                or isinstance(envelope.get("timestamp"), bool)
                or envelope.get("delivery_id") != record.get("question_delivery_id")
                or envelope.get("sequence") != record.get("sequence")
                or envelope.get("timestamp") != record.get("timestamp")
                or envelope.get("sender_id") != modeling
                or envelope.get("recipient_id") != coordinator
                or envelope.get("text") != record.get("text")
                or envelope.get("expects_reply") is not True
                or envelope.get("reply_to_delivery_id") is not None
            ):
                raise TeamConfigurationError("outer question display envelope drifts")
            if (
                record.get("run_id") != self.run.run_id
                or record.get("project_id") != project_id
                or record.get("origin_agent_id") != modeling
            ):
                raise TeamConfigurationError("outer question display binding drifts")
            if record.get("displayed") is True or record.get("consumed") is True:
                continue
            if delivery_id not in seen:
                records_to_display.append(record)
                seen.add(delivery_id)

        # Persist each record before flipping its in-memory display bit.  If a
        # later independent append fails, the already evidenced records remain
        # valid while the caller aborts before it can consume another input.
        for record in records_to_display:
            self._append_evidence(
                "outer-question",
                {
                    key: record[key]
                    for key in ("question_delivery_id", "project_id", "run_id", "text")
                },
            )
            record["displayed"] = True

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
        failures = self._consume_runtime_failures()
        if failures:
            return self._finalize_runtime_failure(failures)
        try:
            self._check_formal_candidate_progress()
        except FormalCandidateProgressTimeout:
            self._latch_formal_candidate_failure("collaboration/routing", "candidate-progress-timeout")
            raise
        output: list[dict[str, Any]] = []
        self._handle_issue_events(output)
        if self._issue_abort_requested:
            cleanup = self.cleanup()
            issue = self._issue_ledger().active_issue if self._issue_ledger() is not None else None
            self._record_issue_abort_terminal_failure(issue, cleanup)
            output.append(
                {
                    "type": "issue-aborted",
                    "issue_id": issue.issue_id if issue else None,
                    "cleanup": cleanup,
                }
            )
            self._state(
                "TERMINAL_REPORT_COMPLETE",
                issue_abort=True,
                issue_id=issue.issue_id if issue else None,
            )
            return output
        self._drain_coordination_runtime_deliveries()
        issue_ledger = self._issue_ledger()
        issue_pending = bool(issue_ledger is not None and issue_ledger.pending)
        coordinator = next(
            agent.agent_id
            for agent in self.run.configuration.profile.agents
            if agent.package.role == "coordinator"
        )
        deliveries = self.transport.drain()
        if issue_pending:
            # Preserve every ordinary delivery/reply slot while the cooperative
            # issue is waiting.  The Broker history remains immutable and no
            # candidate response can be accidentally consumed before guidance.
            self.transport.requeue(deliveries)
            # Pump App-Server notifications while the run is paused so the
            # Coordinator's issue_control callback can enter the queue.  No
            # ordinary peer/terminal Runtime message is delivered or consumed.
            self.adapter.receive_messages()
            failures = self._consume_runtime_failures()
            if failures:
                return self._finalize_runtime_failure(failures)
            # The original candidate dispatch may complete while the issue is
            # pending.  Observe that completion now, before a later pause/
            # recovery turn overwrites the Runtime's last-completed turn ID.
            # Keep the issue freeze intact: redrive and deadline checks remain
            # deferred until the issue has been resolved.
            if self._candidate_progress is not None:
                roles = self._formal_candidate_roles()
                states_reader = getattr(self.adapter, "get_agent_states", None)
                if roles is not None and callable(states_reader):
                    _, protocol = roles
                    self._candidate_progress.observe_states(
                        states_reader(), protocol_agent_id=protocol
                    )
            return output
        for delivery in deliveries:
            try:
                formal_candidate_event = self._observe_formal_candidate_delivery(delivery)
            except FormalCandidateError as exc:
                self._latch_formal_candidate_failure("modeling-quality", "candidate-envelope-invalid")
                raise TeamConfigurationError(str(exc)) from exc
            self._register_stage_handoff_delivery_if_exact(delivery)
            formal_invalid_response = False
            formal_roles = self._formal_candidate_roles()
            if formal_roles is not None and self._candidate_progress is not None:
                modeling, protocol = formal_roles
                formal_invalid_response = self._candidate_progress.is_invalid_response(
                    delivery,
                    modeling_agent_id=modeling,
                    protocol_agent_id=protocol,
                )
                if formal_invalid_response:
                    identity = self._candidate_progress.identity
                    if identity is None:
                        raise FormalCandidateError(
                            "formal invalid response has no active candidate identity"
                        )
                    standalone_response = (
                        delivery.sender_id == protocol
                        and delivery.recipient_id == modeling
                        and delivery.expects_reply is True
                        and delivery.reply_to_delivery_id is None
                    )
                    if standalone_response:
                        self.transport.ack_delivery(delivery.delivery_id)
                        self._append_evidence(
                            "formal-candidate-progress",
                            {
                                "event": "invalid-standalone-conflict-quarantined",
                                "state": self._candidate_progress.state,
                                "original_delivery_id": identity.original_delivery_id,
                                "invalid_reply_delivery_id": delivery.delivery_id,
                            },
                        )
                        continue
                    try:
                        self.transport.reopen_formal_reply_slot(
                            original_delivery_id=identity.original_delivery_id,
                            invalid_reply_delivery_id=delivery.delivery_id,
                            modeling_agent_id=modeling,
                            protocol_agent_id=protocol,
                            formal_candidate=True,
                        )
                    except RoutingError:
                        self._latch_formal_candidate_failure(
                            "collaboration/routing", "formal-reply-slot-reopen-rejected"
                        )
                        raise
                    self._append_evidence(
                        "formal-candidate-progress",
                        {
                            "event": "invalid-response-slot-reopened",
                            "state": self._candidate_progress.state,
                            "original_delivery_id": identity.original_delivery_id,
                            "invalid_reply_delivery_id": delivery.delivery_id,
                        },
                    )
                    # An invalid formal response is a transport-level recovery
                    # artifact, not a peer message.  Do not expose free text or
                    # malformed receipt payloads to Modeling: doing so would let
                    # the payload become a second, non-formal reply anchor (for
                    # example, a revision replying to an invalid guidance ID).
                    # The original formal slot was already reopened above, so the
                    # next candidate redrive can elicit one canonical conflict or
                    # receipt from Protocol.
                    self.transport.ack_delivery(delivery.delivery_id)
                    self._append_evidence(
                        "formal-candidate-progress",
                        {
                            "event": "invalid-response-quarantined",
                            "state": self._candidate_progress.state,
                            "original_delivery_id": identity.original_delivery_id,
                            "invalid_reply_delivery_id": delivery.delivery_id,
                        },
                    )
                    continue
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
                dispatch_receipt = self.adapter.send_message(delivery.recipient_id, runtime_delivery)
                if formal_candidate_event in {"candidate", "revision"}:
                    assert self._candidate_progress is not None
                    self._candidate_progress.bind_dispatch(
                        dispatch_receipt, now=self.monotonic_clock()
                    )
            except FormalCandidatePlatformContractError:
                self._latch_formal_candidate_failure("platform-contract", "turn-binding-missing")
                raise
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
        messages = self.adapter.receive_messages()
        failures = self._consume_runtime_failures()
        if failures:
            return self._finalize_runtime_failure(failures)
        try:
            if self._candidate_progress is not None:
                roles = self._formal_candidate_roles()
                states_reader = getattr(self.adapter, "get_agent_states", None)
                if roles is not None and callable(states_reader):
                    _, protocol = roles
                    self._candidate_progress.observe_states(
                        states_reader(), protocol_agent_id=protocol
                    )
                self._maybe_redrive_formal_candidate()
                self._check_formal_candidate_progress()
        except FormalCandidateProgressTimeout:
            self._latch_formal_candidate_failure("collaboration/routing", "candidate-progress-timeout")
            raise
        except FormalCandidateRoutingError:
            self._latch_formal_candidate_failure("collaboration/routing", "candidate-redrive-exhausted")
            raise
        except FormalCandidatePlatformContractError:
            self._latch_formal_candidate_failure("platform-contract", "turn-binding-missing")
            raise
        for message in messages:
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
            or (
                self.acceptance is not None
                and self.acceptance.is_settled
                and not (
                    self._issue_ledger() is not None
                    and self._issue_ledger().pending
                )
            )
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
        issue_ledger = self._issue_ledger()
        if issue_ledger is not None and issue_ledger.pending and not self._issue_abort_requested:
            active = issue_ledger.active_issue
            paused = {
                "status": "paused",
                "issue_id": active.issue_id if active else None,
                "state": issue_ledger.state,
                "cleanup_deferred": True,
            }
            self._state(
                "WAITING_REPAIR"
                if issue_ledger.state == "waiting_repair"
                else "WAITING_OWNER",
                issue_id=paused["issue_id"],
            )
            return paused
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
            if self._modeling_read_lifecycle is not None and self.run is not None:
                key_id = self.run.modeling_read_key_id
                if isinstance(key_id, str) and key_id:
                    try:
                        revoked = self._modeling_read_lifecycle.revoke(key_id)
                        evidence["modeling_read_key"] = {
                            "key_id": revoked.key_id,
                            "status": revoked.status,
                            "revoked_at": revoked.revoked_at,
                            **self._modeling_read_lifecycle.evidence(key_id),
                        }
                    except Exception as exc:
                        evidence["modeling_read_key_cleanup_error"] = type(exc).__name__
                if self._modeling_read_proxy is not None:
                    self._modeling_read_proxy.destroy()
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
                "transport_interventions_sha256": digest_file(
                    self.repository_root / "modeling_team/interventions.py"
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
                getattr(self._ledger, "requirement_id", None)
                in {R2_3_005_REQUIREMENT_ID, "R2.3-003"}
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

    def _formal_coordination_role_ids(self) -> dict[str, str]:
        """Resolve formal coordination roles to their configured agent IDs."""

        configuration = getattr(self.run, "configuration", None)
        profile = getattr(configuration, "profile", None)
        agents = getattr(profile, "agents", None)
        required_roles = {"coordinator", "modeling", "protocol", "acceptance"}
        if not isinstance(agents, (list, tuple)):
            raise TeamConfigurationError("formal coordination role identities are unavailable")
        role_ids: dict[str, str] = {}
        for agent in agents:
            package = getattr(agent, "package", None)
            role = getattr(package, "role", None)
            agent_id = getattr(agent, "agent_id", None)
            if (
                not isinstance(role, str)
                or role not in required_roles
                or role in role_ids
                or not isinstance(agent_id, str)
                or not agent_id
            ):
                raise TeamConfigurationError("formal coordination role identities are invalid")
            role_ids[role] = agent_id
        if set(role_ids) != required_roles:
            raise TeamConfigurationError("formal coordination role identities are incomplete")
        return role_ids

    def _coordination_transport_event_observer(self, event: dict[str, object]) -> None:
        """Persist a coordination event, then queue its Runner-owned delivery.

        ``TeamTransportBroker.send_coordination`` invokes the observer only after
        the phase callback has accepted the message and after it has released the
        Broker state lock.  The observer itself must remain non-reentrant: it
        records the immutable coordination evidence first and only then queues a
        validated phase delivery for the Runner's next ``drain`` turn.  Readiness,
        silence, and verdict-route signals go to Coordinator; only
        ``acceptance_start`` goes to Acceptance.
        """

        self._append_coordination_transport_event(event)
        if (
            not isinstance(event, dict)
            or not isinstance(event.get("message_kind"), str)
            or event.get("message_kind")
            not in {
                "ready_for_acceptance",
                "silent_for_acceptance",
                "acceptance_start",
                "acceptance_verdict_route",
            }
            or not isinstance(event.get("sender_id"), str)
            or not isinstance(event.get("message_id"), str)
            or not event.get("message_id")
            or not isinstance(event.get("recipient_id"), str)
            or not isinstance(event.get("text"), str)
            or not isinstance(event.get("phase_event"), dict)
        ):
            return
        message_kind = event["message_kind"]
        sender_id = event["sender_id"]
        recipient_id = event["recipient_id"]
        role_ids = self._formal_coordination_role_ids()
        expected_sender, expected_recipient = {
            "ready_for_acceptance": (role_ids["modeling"], role_ids["coordinator"]),
            "silent_for_acceptance": (role_ids["protocol"], role_ids["coordinator"]),
            "acceptance_start": (role_ids["coordinator"], role_ids["acceptance"]),
            "acceptance_verdict_route": (role_ids["acceptance"], role_ids["coordinator"]),
        }[message_kind]
        if sender_id != expected_sender or recipient_id != expected_recipient:
            raise TeamConfigurationError("coordination Runtime delivery binding is invalid")
        generation = event["phase_event"].get("generation")
        if not isinstance(generation, int) or isinstance(generation, bool) or generation <= 0:
            error = (
                "Acceptance start generation is invalid"
                if message_kind == "acceptance_start"
                else "coordination Runtime delivery generation is invalid"
            )
            raise TeamConfigurationError(error)
        queued = {
            "message_id": event["message_id"],
            "recipient_id": recipient_id,
            "message_kind": message_kind,
            "sender_id": sender_id,
            "text": event["text"],
            "generation": generation,
        }
        with self._coordination_runtime_lock:
            message_id = queued["message_id"]
            message_ids = getattr(self, "_coordination_runtime_message_ids", None)
            if not isinstance(message_ids, set):
                message_ids = set()
                self._coordination_runtime_message_ids = message_ids
            if message_id in message_ids:
                raise TeamConfigurationError("coordination Runtime delivery was queued twice")
            signal_keys = getattr(self, "_coordination_runtime_signal_keys", None)
            if not isinstance(signal_keys, set):
                signal_keys = set()
                self._coordination_runtime_signal_keys = signal_keys
            if message_kind in {"ready_for_acceptance", "silent_for_acceptance"}:
                signal_key = f"{generation}:{message_kind}:{sender_id}"
                if signal_key in signal_keys:
                    raise TeamConfigurationError("coordination readiness delivery was queued twice")
                signal_keys.add(signal_key)
            message_ids.add(message_id)
            self._coordination_runtime_queue.append(queued)

    def _drain_coordination_runtime_deliveries(self) -> None:
        """Dispatch queued coordination deliveries outside Broker callback locks."""

        with self._coordination_runtime_lock:
            queued, self._coordination_runtime_queue = self._coordination_runtime_queue, []
        if not queued:
            return
        role_ids = self._formal_coordination_role_ids()
        for event in queued:
            recipient_id = event.get("recipient_id")
            message_id = event.get("message_id")
            message_kind = event.get("message_kind")
            sender_id = event.get("sender_id")
            text = event.get("text")
            generation = event.get("generation")
            if (
                message_kind
                not in {
                    "ready_for_acceptance",
                    "silent_for_acceptance",
                    "acceptance_start",
                    "acceptance_verdict_route",
                }
                or not isinstance(message_id, str)
                or not message_id
                or not isinstance(sender_id, str)
                or not isinstance(text, str)
                or not isinstance(generation, int)
                or isinstance(generation, bool)
                or generation <= 0
            ):
                error = (
                    "Acceptance start delivery binding is invalid"
                    if message_kind == "acceptance_start"
                    else "coordination Runtime delivery binding is invalid"
                )
                raise TeamConfigurationError(error)
            expected_sender, expected_recipient = {
                "ready_for_acceptance": (role_ids["modeling"], role_ids["coordinator"]),
                "silent_for_acceptance": (role_ids["protocol"], role_ids["coordinator"]),
                "acceptance_start": (role_ids["coordinator"], role_ids["acceptance"]),
                "acceptance_verdict_route": (role_ids["acceptance"], role_ids["coordinator"]),
            }[message_kind]
            if sender_id != expected_sender or recipient_id != expected_recipient:
                error = (
                    "Acceptance start delivery binding is invalid"
                    if message_kind == "acceptance_start"
                    else "coordination Runtime delivery binding is invalid"
                )
                raise TeamConfigurationError(error)
            if message_kind == "acceptance_start":
                if self.acceptance is None or recipient_id != self.acceptance.acceptance_id:
                    raise TeamConfigurationError("Acceptance start delivery binding is invalid")
                payload = {
                    "acceptance_id": self.acceptance.acceptance_id,
                    "round_id": text,
                    "generation": generation,
                    "coordination_message_id": message_id,
                }
                delivery_kind = "acceptance-start"
            else:
                payload = {
                    "coordination_message_id": message_id,
                    "generation": generation,
                    "message_kind": message_kind,
                    "sender_id": sender_id,
                    "recipient_id": recipient_id,
                    "text": text,
                }
                delivery_kind = "coordination-phase"
            try:
                self.adapter.send_message(
                    recipient_id,
                    RuntimeDelivery(
                        sender_id="runner/coordination",
                        recipient_id=recipient_id,
                        kind=delivery_kind,
                        text=json.dumps(payload, ensure_ascii=False, sort_keys=True),
                        delivery_id=message_id,
                    ),
                )
            except Exception as exc:
                self._state("FAILED", coordination_message_id=message_id)
                error = (
                    "Acceptance start delivery failed"
                    if message_kind == "acceptance_start"
                    else "coordination Runtime delivery failed"
                )
                raise TeamConfigurationError(error) from exc

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
