"""Requirement-owned formal Team Runner contracts.

The formal runner intentionally has a very small, closed registry.  A profile and
task are not a plug-in API: they are an exact pair belonging to one reviewed
requirement.  Keeping the identity in one module prevents the 005 ``create``
contract from accidentally accepting the 003 ``existing`` assets (or vice versa).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import TeamConfiguration, TeamConfigurationError, load_formal_team_configuration
from .r23003_contract import (
    R2_3_003_TARGET_CLASS,
    R2_3_003_TARGET_IDS,
    deletion_policy,
    validate_deletion_policy,
)


@dataclass(frozen=True)
class FormalRunContract:
    requirement_id: str
    contract_id: str
    profile_id: str
    task_id: str
    scope_mode: str
    default_model_profile_id: str
    acceptance_standard_path: str
    scope_config_path: str | None = None
    source_manifest_path: str | None = None
    ledger_requirement_id: str | None = None
    deletion_policy: dict[str, Any] | None = None

    @property
    def is_existing(self) -> bool:
        return self.scope_mode == "existing"


R2_3_005_CONTRACT = FormalRunContract(
    requirement_id="R2.3-005",
    contract_id="r2-3-005-formal-create",
    profile_id="r2-3-005-modeling-team",
    task_id="r2-3-005-formal-acceptance",
    scope_mode="create",
    default_model_profile_id="deepseek-v4-flash-max",
    acceptance_standard_path="modeling_team/references/r2-3-005-acceptance-standard.json",
    ledger_requirement_id="R2.3-005",
)

R2_3_003_CONTRACT = FormalRunContract(
    requirement_id="R2.3-003",
    contract_id="r2-3-003-existing-incremental",
    profile_id="r2-3-003-modeling-team",
    task_id="r2-3-003-existing-scope-incremental",
    scope_mode="existing",
    default_model_profile_id="deepseek-v4-flash-max",
    acceptance_standard_path="modeling_team/references/r2-3-003-acceptance-standard.json",
    scope_config_path="modeling_team/scopes/r2-3-003-existing.yaml",
    source_manifest_path="docs/evaluation-scenarios/ontology-modeling-team-r2-3-003/agent-input/manifest.json",
    ledger_requirement_id="R2.3-003",
    deletion_policy=deletion_policy(),
)

R2_3_008_CONTRACT = FormalRunContract(
    requirement_id="R2.3-008",
    contract_id="r2-3-008-luna-route-create",
    profile_id="r2-3-008-modeling-team",
    task_id="r2-3-008-formal-acceptance",
    scope_mode="create",
    default_model_profile_id="openai-luna-medium",
    acceptance_standard_path="modeling_team/references/r2-3-008-acceptance-standard.json",
    ledger_requirement_id="R2.3-008",
)

FORMAL_RUN_CONTRACTS: tuple[FormalRunContract, ...] = (
    R2_3_005_CONTRACT,
    R2_3_003_CONTRACT,
    R2_3_008_CONTRACT,
)


def formal_run_contract_for(
    configuration: TeamConfiguration | None = None,
    *,
    profile_id: str | None = None,
    task_id: str | None = None,
) -> FormalRunContract | None:
    """Return the exact known contract, or ``None`` for non-formal fixtures."""

    if configuration is not None:
        profile = getattr(configuration, "profile", None)
        task = getattr(configuration, "task", None)
        profile_id = getattr(profile, "profile_id", None)
        task_id = getattr(task, "task_id", None)
    if not isinstance(profile_id, str) or not isinstance(task_id, str):
        return None
    for contract in FORMAL_RUN_CONTRACTS:
        if profile_id == contract.profile_id and task_id == contract.task_id:
            return contract
    return None


def require_formal_run_contract(configuration: TeamConfiguration) -> FormalRunContract:
    """Fail closed for unknown or cross-wired formal identities."""

    contract = formal_run_contract_for(configuration)
    if contract is None:
        raise TeamConfigurationError("unknown or cross-wired formal run contract")
    return contract


def validate_formal_run_contract_assets(contract: FormalRunContract) -> None:
    """Validate requirement-owned deletion policy before any run side effect."""

    if contract.requirement_id != "R2.3-003":
        if contract.deletion_policy is not None:
            raise TeamConfigurationError("deletion policy is restricted to R2.3-003")
        return
    try:
        policy = validate_deletion_policy(contract.deletion_policy)
    except ValueError as exc:
        raise TeamConfigurationError(str(exc)) from exc
    if tuple(item["semantic_id"] for item in policy["targets"]) != R2_3_003_TARGET_IDS:
        raise TeamConfigurationError("R2.3-003 target IDs drift")
    if any(item["expected_class"] != R2_3_003_TARGET_CLASS for item in policy["targets"]):
        raise TeamConfigurationError("R2.3-003 target Class drifts")


def _relative(root: Path, path: Path, field: str) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, RuntimeError, ValueError) as exc:
        raise TeamConfigurationError(f"formal {field} escapes repository") from exc


def load_formal_run_configuration(
    profile_path: Path,
    task_path: Path,
    *,
    root: Path | None = None,
) -> tuple[TeamConfiguration, FormalRunContract]:
    """Load a reviewed formal pair and verify its requirement-owned assets.

    The returned configuration still contains the generic Profile/Task objects;
    the second value carries the closed identity and policy mapping used by the
    Runner.  Every check is read-only and happens before a run root or ledger is
    touched.
    """

    root = (root or Path(__file__).resolve().parents[1]).resolve()
    configuration = load_formal_team_configuration(profile_path, task_path, root=root)
    contract = require_formal_run_contract(configuration)
    validate_formal_run_contract_assets(contract)
    expected_profile = root / ("modeling_team/profiles/" + contract.profile_id + ".yaml")
    # The 003 profile has a descriptive filename; identity is still exact.
    if contract is R2_3_003_CONTRACT:
        expected_profile = root / "modeling_team/profiles/r2-3-003-existing-scope-modeling-team.yaml"
    expected_task = root / ("modeling_team/tasks/" + contract.task_id + ".yaml")
    if _relative(root, Path(profile_path), "Profile") != _relative(root, expected_profile, "Profile"):
        raise TeamConfigurationError("formal Profile path is not the authoritative contract asset")
    if _relative(root, Path(task_path), "Task") != _relative(root, expected_task, "Task"):
        raise TeamConfigurationError("formal Task path is not the authoritative contract asset")

    parameters = configuration.profile.parameters
    if parameters.get("formal_contract") != contract.contract_id:
        raise TeamConfigurationError("formal Profile contract binding drifts")
    if parameters.get("acceptance_standard") != contract.acceptance_standard_path:
        raise TeamConfigurationError("formal Profile acceptance standard binding drifts")
    if contract.scope_config_path is not None:
        if parameters.get("scope_config") != contract.scope_config_path:
            raise TeamConfigurationError("formal Profile scope config binding drifts")
        if parameters.get("source_manifest") != contract.source_manifest_path:
            raise TeamConfigurationError("formal Profile source manifest binding drifts")

    for field, relative in (
        ("model profile", f"modeling_team/model-profiles/{contract.default_model_profile_id}.yaml"),
        ("acceptance standard", contract.acceptance_standard_path),
        ("scope config", contract.scope_config_path),
        ("source manifest", contract.source_manifest_path),
    ):
        if relative is None:
            continue
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise TeamConfigurationError(f"formal {field} is unavailable")

    # Required task-input fields are part of the role contract.  This catches a
    # profile accidentally pointing at a package with an incompatible prompt
    # surface before any Runtime process is launched.
    required_by_role: dict[str, set[str]] = {
        "coordinator": {"task", "allowed_sources", "roster"},
        "modeling": {"task", "allowed_sources", "roster"},
        "protocol": {"task", "allowed_sources", "roster"},
        "acceptance": {"task", "acceptance_ticket", "examiner_reports", "roster"},
    }
    for agent in configuration.profile.agents:
        required = required_by_role.get(agent.package.role, set())
        declared = agent.package.task_input.get("required")
        if not isinstance(declared, list) or not required.issubset(set(declared)):
            raise TeamConfigurationError(
                f"formal Package {agent.package.package_id} task input is incompatible"
            )
    return configuration, contract


__all__ = [
    "FORMAL_RUN_CONTRACTS",
    "R2_3_003_CONTRACT",
    "R2_3_005_CONTRACT",
    "R2_3_008_CONTRACT",
    "FormalRunContract",
    "formal_run_contract_for",
    "load_formal_run_configuration",
    "require_formal_run_contract",
    "validate_formal_run_contract_assets",
]
