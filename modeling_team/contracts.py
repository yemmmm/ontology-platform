"""Runtime-neutral Profile, Package, and Task contracts for R2.3-001."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SAFE_ID = re.compile(r"^[a-z][a-z0-9-]{1,79}$")
FORBIDDEN_KEYS = {
    "key",
    "token",
    "secret",
    "credential",
    "project_id",
    "ontology_id",
    "thread_id",
    "pid",
}
PLATFORM_VALUES = {"none", "read", "write"}
# ``source-specialist`` remains readable for archived R2.3-001/R2.3-002 evidence
# and deterministic legacy fixtures.  Formal R2.3-005 loading uses
# ``FORMAL_ROLE_VALUES`` below and rejects it before scope or Agent startup.
ROLE_VALUES = {"coordinator", "modeling", "protocol", "source-specialist", "acceptance"}
FORMAL_ROLE_VALUES = {"coordinator", "modeling", "protocol", "acceptance"}
# R3.0-011: the competency-question role is registered in its own closed set so
# every pre-existing ``ROLE_VALUES`` contract (R2.3 formal loading, R3.0-002
# multi-slice assertions) stays byte-identical.  ``ADMITTED_ROLE_VALUES`` is the
# single loader-wide registration point used by the package loader.
COMPETENCY_QUESTION_ROLE = "competency-question"
COMPETENCY_QUESTION_ROLE_VALUES = frozenset({COMPETENCY_QUESTION_ROLE})
ADMITTED_ROLE_VALUES = ROLE_VALUES | set(COMPETENCY_QUESTION_ROLE_VALUES)
# R3.0-002 non-formal multi-slice roster: exactly the three modeling roles.
# Acceptance stays out until the R3.0-006 real-run requirement adds it.
MULTI_SLICE_ROLE_VALUES = {"coordinator", "modeling", "protocol"}
# The v2 Task may narrow this set, but never broaden it.  Keep lifecycle/key/project
# mechanics outside the Agent-visible platform surface.
SAFE_PROTOCOL_TOOLS = frozenset(
    {
        "check_platform_health",
        "get_project_build_context",
        "get_ontology_workspace_context",
        "create_build_session",
        "get_build_session",
        "save_build_checkpoint",
        "complete_build_session",
        "cancel_build_session",
        "acquire_ontology_lease",
        "renew_ontology_lease",
        "release_ontology_lease",
        "submit_modeling_batch",
        "get_modeling_batch",
        "list_session_modeling_batches",
        "list_ontology_modeling_batches",
        "get_modeling_context",
        "get_ontology_read_model",
        "query_semantic_context",
        "run_semantic_validation",
        "run_semantic_reasoning",
        "get_ontology_lineage",
        "inspect_semantic_statement_provenance",
    }
)
# R2.3-003 extends the ordinary read allowlist with the generic, opaque-cursor
# entity statement projection.  Keep the historical SAFE_PROTOCOL_TOOLS value
# byte-compatible for 005/legacy task and P2 driver contracts.
SAFE_PROTOCOL_TOOLS_R23003 = SAFE_PROTOCOL_TOOLS | {"get_entity_statement_context"}
# R3.0-002 extends the ordinary allowlist with the six R3.0-004 protection-set
# MCP tools (model scope, exact registered names in
# backend/app/mcp/tools/protection_sets.py).  SAFE_PROTOCOL_TOOLS itself stays
# byte-unchanged for every pre-existing task and P2 driver contract.
SEMANTIC_PROTECTION_SET_TOOLS = frozenset(
    {
        "list_semantic_protection_sets",
        "create_semantic_protection_set",
        "update_semantic_protection_set",
        "delete_semantic_protection_set",
        "add_semantic_protection_set_members",
        "remove_semantic_protection_set_members",
    }
)
SAFE_PROTOCOL_TOOLS_R30002 = SAFE_PROTOCOL_TOOLS | SEMANTIC_PROTECTION_SET_TOOLS
SOURCE_CLASSIFICATIONS = {"business-source", "coordination", "protocol", "consumer-question"}
_FORMAL_PROFILE_IDS = frozenset(
    {"r2-3-005-modeling-team", "r2-3-003-modeling-team", "r2-3-008-modeling-team",
     "r2-3-009-modeling-team"}
)
# Closed registry for the R3.0-002 non-formal multi-slice Profile kind, mirroring
# the formal cross-wire guard pattern.
MULTI_SLICE_PROFILE_IDS = frozenset({"r3-0-002-modeling-team"})
# R3.0-011: the competency-question Profile is the second registered multi-slice
# Profile (three production roles plus one competency-question Agent).
COMPETENCY_QUESTION_PROFILE_IDS = frozenset({"r3-0-011-competency-question"})
# R2.3-009 T3: ``run_fallback_timeout_seconds`` stays a governed knob, but the
# competency-question Profile may carry it too.  Run r30006-20260912-glmb01-start1
# consumed the entire 10800s default in genuine active work (0 nudges, 0 open
# issues) and was latched run-fallback-timeout at the start of the
# analyzed-conclusions phase; the profile needs the bounded magnitude knob, and
# ``_validate_run_fallback_timeout`` still caps whatever it carries.  The other
# tier parameters remain formal-Profile-only.
_RUN_FALLBACK_TIMEOUT_PROFILE_IDS = _FORMAL_PROFILE_IDS | COMPETENCY_QUESTION_PROFILE_IDS
# R3.0-002 Task ``parameters`` is a closed, optional key set on the v2 Task.
MULTI_SLICE_TASK_PARAMETER = "multi_slice_workflow"
# R3.0-008B segment 1: staged modeling decisions extend the same closed set.
STAGED_MODELING_DECISIONS_PARAMETER = "staged_modeling_decisions"
# R3.0-009: the unified semantic graph is the third, opt-in member of the set.
UNIFIED_GRAPH_TASK_PARAMETER = "unified_semantic_graph"
# R3.0-011: competency-question batch acceptance is the fourth opt-in member.
COMPETENCY_QUESTION_ACCEPTANCE_PARAMETER = "competency_question_acceptance"
# R3.0-012: the acceptance-target selector is the fifth opt-in member and the
# first non-boolean one -- a closed two-value enum naming which acceptance
# scope the run freezes.  Omission is equivalent to ``full_joint``; the
# normalized value is what the Runner writes into its configuration snapshot,
# never a re-derivation after start.  The draft name ``parameters.acceptance_scope``
# was never implemented and is deliberately not an alias (design §2.2).
ACCEPTANCE_TARGET_PARAMETER = "acceptance_target"
ACCEPTANCE_TARGET_FULL_JOINT = "full_joint"
ACCEPTANCE_TARGET_CQ_SEMANTIC = "cq_semantic"
ACCEPTANCE_TARGET_VALUES = frozenset(
    {ACCEPTANCE_TARGET_FULL_JOINT, ACCEPTANCE_TARGET_CQ_SEMANTIC}
)
# R3.0-015 S1: the modeling-checkpoint selector is the sixth opt-in member.
# It enables persistent stage-result save/inspect only (never a resume
# capability) and requires the staged unified path it saves from.
MODELING_CHECKPOINTS_PARAMETER = "modeling_checkpoints"
_TASK_PARAMETER_NAMES = frozenset(
    {
        MULTI_SLICE_TASK_PARAMETER,
        STAGED_MODELING_DECISIONS_PARAMETER,
        UNIFIED_GRAPH_TASK_PARAMETER,
        COMPETENCY_QUESTION_ACCEPTANCE_PARAMETER,
        ACCEPTANCE_TARGET_PARAMETER,
        MODELING_CHECKPOINTS_PARAMETER,
    }
)
_CANDIDATE_PROGRESS_TIMEOUT_PARAMETER = "candidate_progress_timeout_seconds"
_CANDIDATE_PROGRESS_TIMEOUT_MAX = 600.0
# R2.3-009 timeout tiers: bounded nudge quota, cooperative-escalation repeat
# threshold, and the run-level fallback active-clock budget.
_CANDIDATE_REDRIVE_LIMIT_PARAMETER = "candidate_redrive_limit"
_FEEDBACK_ESCALATION_REPEAT_PARAMETER = "feedback_escalation_repeat"
_RUN_FALLBACK_TIMEOUT_PARAMETER = "run_fallback_timeout_seconds"
_RUN_FALLBACK_TIMEOUT_MAX = 24 * 3600.0


def _validate_candidate_progress_timeout(value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TeamConfigurationError("candidate progress timeout is invalid")
    try:
        normalized = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise TeamConfigurationError("candidate progress timeout is invalid") from exc
    if not math.isfinite(normalized) or not 0 < normalized <= _CANDIDATE_PROGRESS_TIMEOUT_MAX:
        raise TeamConfigurationError("candidate progress timeout is invalid")


def _validate_positive_int_parameter(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise TeamConfigurationError(f"{name} is invalid")


def _validate_run_fallback_timeout(value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TeamConfigurationError("run fallback timeout is invalid")
    try:
        normalized = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise TeamConfigurationError("run fallback timeout is invalid") from exc
    if not math.isfinite(normalized) or not 0 < normalized <= _RUN_FALLBACK_TIMEOUT_MAX:
        raise TeamConfigurationError("run fallback timeout is invalid")


class TeamConfigurationError(ValueError):
    """A configuration condition that must fail before scope or Agent startup."""


@dataclass(frozen=True)
class AgentPackage:
    package_id: str
    role: str
    description: str
    instructions_path: Path
    required_skills: tuple[Path, ...]
    references: tuple[Path, ...]
    permissions: dict[str, Any]
    runtime: dict[str, Any]
    task_input: dict[str, Any]


@dataclass(frozen=True)
class ProfileAgent:
    agent_id: str
    package: AgentPackage


@dataclass(frozen=True)
class TeamProfile:
    profile_id: str
    runtime: str
    agents: tuple[ProfileAgent, ...]
    communication: frozenset[tuple[str, str]]
    parameters: dict[str, Any]
    expected_matrix_binding: dict[str, str] | None = None


@dataclass(frozen=True)
class TeamTask:
    task_id: str
    objective: str
    allowed_sources: tuple[Path, ...]
    expected_terminal_evidence: tuple[str, ...]
    schema_version: int = 1
    role_sources: tuple["TaskSource", ...] = ()
    protocol_tools: tuple[str, ...] = ()
    retain_nonempty: bool = False
    semantic_start_evidence: tuple[str, ...] = ()
    expected_matrix_binding: dict[str, str] | None = None
    parameters: dict[str, Any] | None = None


@dataclass(frozen=True)
class TaskSource:
    path: Path
    relative_path: Path
    classification: str
    roles: frozenset[str]


@dataclass(frozen=True)
class TeamConfiguration:
    profile: TeamProfile
    task: TeamTask


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _safe_id(value: object, field: str) -> str:
    if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
        raise TeamConfigurationError(f"{field} must be a safe stable identifier")
    return value


_MATRIX_BINDING_FIELDS = (
    "proof_matrix_path",
    "proof_matrix_digest",
    "p2a_pass_path",
    "p2a_pass_digest",
    "source_run_id",
)
_STATIC_MATRIX_BINDING_FIELDS = {
    "proof_matrix_path",
    "proof_matrix_digest",
    "p2a_pass_path",
    "source_run_id",
}
_STATIC_MATRIX_BINDING_WITH_SOURCE_FIELDS = _STATIC_MATRIX_BINDING_FIELDS | {
    "source_candidate_digest",
}


def _expected_matrix_binding(value: object, *, location: str) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) not in (
        set(_MATRIX_BINDING_FIELDS),
        _STATIC_MATRIX_BINDING_FIELDS,
        _STATIC_MATRIX_BINDING_WITH_SOURCE_FIELDS,
    ):
        raise TeamConfigurationError(f"{location} expected_matrix_binding fields drift")
    result: dict[str, str] = {}
    for field in value:
        raw = value.get(field)
        if not isinstance(raw, str) or not raw:
            raise TeamConfigurationError(f"{location} expected_matrix_binding {field} is invalid")
        result[field] = raw
    for field in ("proof_matrix_digest", "p2a_pass_digest", "source_candidate_digest"):
        if field not in result:
            continue
        if len(result[field]) != 64:
            raise TeamConfigurationError(f"{location} expected_matrix_binding {field} is invalid")
        try:
            int(result[field], 16)
        except ValueError as exc:
            raise TeamConfigurationError(
                f"{location} expected_matrix_binding {field} is invalid"
            ) from exc
    if result["proof_matrix_path"].startswith("/") or result["p2a_pass_path"].startswith("/"):
        raise TeamConfigurationError(f"{location} expected_matrix_binding path is invalid")
    return result


def _yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise TeamConfigurationError(f"cannot load {path}") from exc
    if not isinstance(value, dict):
        raise TeamConfigurationError(f"{path} must contain an object")
    return value


def _reject_forbidden(value: object, *, location: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise TeamConfigurationError(f"{location} has a non-string key")
            if key.lower() in FORBIDDEN_KEYS:
                raise TeamConfigurationError(f"{location} cannot contain {key}")
            _reject_forbidden(child, location=location)
    elif isinstance(value, list):
        for child in value:
            _reject_forbidden(child, location=location)


def _repo_path(
    root: Path, value: object, *, field: str, directory: bool = False
) -> Path:
    if not isinstance(value, str) or not value:
        raise TeamConfigurationError(f"{field} must be a repository-relative path")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise TeamConfigurationError(f"{field} escapes repository")
    raw = root / candidate
    if raw.is_symlink():
        raise TeamConfigurationError(f"{field} is unavailable: {value}")
    resolved = raw.resolve()
    if root not in resolved.parents and resolved != root:
        raise TeamConfigurationError(f"{field} escapes repository")
    if (
        not (resolved.is_dir() if directory else resolved.is_file())
        or resolved.is_symlink()
    ):
        raise TeamConfigurationError(f"{field} is unavailable: {value}")
    return resolved


def _load_package(root: Path, package_id: str) -> AgentPackage:
    package_dir = _repo_path(
        root,
        f"modeling_team/agent-packages/{package_id}",
        field="package",
        directory=True,
    )
    data = _yaml(package_dir / "package.yaml")
    _reject_forbidden(data, location=f"Package {package_id}")
    if (
        data.get("schema_version") != 1
        or _safe_id(data.get("package_id"), "package_id") != package_id
    ):
        raise TeamConfigurationError(
            f"Package {package_id} schema or identifier is invalid"
        )
    role = data.get("role")
    if role not in ADMITTED_ROLE_VALUES:
        raise TeamConfigurationError(f"Package {package_id} has unknown role")
    permissions = data.get("permissions")
    if (
        not isinstance(permissions, dict)
        or permissions.get("team_transport") is not True
    ):
        raise TeamConfigurationError(f"Package {package_id} must permit Team Transport")
    platform = permissions.get("platform")
    if platform not in PLATFORM_VALUES:
        raise TeamConfigurationError(
            f"Package {package_id} has invalid platform permission"
        )
    if role == "protocol" and platform != "write":
        raise TeamConfigurationError(
            "Protocol Package must have platform write permission"
        )
    if role not in {"protocol"} and platform != "none":
        raise TeamConfigurationError(
            "only Protocol may have platform permission in R2.3-001"
        )
    if role == "acceptance":
        if permissions.get("source") not in {None, "none"}:
            raise TeamConfigurationError("Acceptance Package cannot read source material")
        if permissions.get("spawn") not in {None, False}:
            raise TeamConfigurationError("Acceptance Package cannot spawn Agents")
        if permissions.get("write") not in {None, False}:
            raise TeamConfigurationError("Acceptance Package cannot write the platform")
    instructions = data.get("instructions")
    if (
        not isinstance(instructions, str)
        or Path(instructions).is_absolute()
        or ".." in Path(instructions).parts
    ):
        raise TeamConfigurationError(
            f"Package {package_id} instructions path is invalid"
        )
    instructions_path = package_dir / instructions
    if not instructions_path.is_file() or instructions_path.is_symlink():
        raise TeamConfigurationError(
            f"Package {package_id} instructions are unavailable"
        )
    skills = data.get("required_skills")
    if not isinstance(skills, list):
        raise TeamConfigurationError(f"Package {package_id} must declare Skills")
    skill_paths = tuple(
        _repo_path(root, entry, field="required_skills") for entry in skills
    )
    if len(set(skill_paths)) != len(skill_paths):
        raise TeamConfigurationError(f"Package {package_id} duplicates a Skill")
    if any(
        "deprecated" in path.as_posix().lower()
        or "deprecated"
        in "\n".join(path.read_text(encoding="utf-8").splitlines()[:5]).lower()
        for path in skill_paths
    ):
        raise TeamConfigurationError(
            f"Package {package_id} references a deprecated Skill"
        )
    refs = data.get("references", [])
    if not isinstance(refs, list):
        raise TeamConfigurationError(f"Package {package_id} references must be a list")
    references = tuple(_repo_path(root, entry, field="references") for entry in refs)
    runtime = data.get("runtime")
    task_input = data.get("task_input")
    if (
        not isinstance(runtime, dict)
        or not isinstance(runtime.get("codex"), dict)
        or not isinstance(task_input, dict)
    ):
        raise TeamConfigurationError(
            f"Package {package_id} loader or task input is invalid"
        )
    sandbox = runtime["codex"].get("sandbox")
    if sandbox not in {"read-only", "workspace-write"}:
        raise TeamConfigurationError(f"Package {package_id} has invalid Codex sandbox")
    return AgentPackage(
        package_id,
        role,
        str(data.get("description", "")),
        instructions_path,
        skill_paths,
        references,
        permissions,
        runtime,
        task_input,
    )


def load_profile(
    path: Path,
    *,
    root: Path | None = None,
    strict: bool = False,
    multi_slice: bool = False,
) -> TeamProfile:
    root = root or repository_root()
    data = _yaml(path)
    _reject_forbidden(data, location="Profile")
    profile_fields = {
        "schema_version",
        "profile_id",
        "runtime",
        "agents",
        "communication",
        "parameters",
    }
    if set(data) != profile_fields and set(data) != profile_fields | {"expected_matrix_binding"}:
        raise TeamConfigurationError("Profile fields drift from schema")
    if data["schema_version"] != 1 or data["runtime"] != "codex":
        raise TeamConfigurationError(
            "only schema v1 homogeneous codex Profiles are supported"
        )
    profile_id = _safe_id(data["profile_id"], "profile_id")
    agents_raw = data["agents"]
    if not isinstance(agents_raw, list) or not agents_raw:
        raise TeamConfigurationError("Profile requires agents")
    agents: list[ProfileAgent] = []
    ids: set[str] = set()
    roles: list[str] = []
    for item in agents_raw:
        if not isinstance(item, dict) or set(item) != {"agent_id", "package"}:
            raise TeamConfigurationError("Profile Agent fields drift")
        agent_id = _safe_id(item["agent_id"], "agent_id")
        if agent_id in ids:
            raise TeamConfigurationError("Profile duplicates Agent ID")
        package = _load_package(root, _safe_id(item["package"], "package"))
        ids.add(agent_id)
        roles.append(package.role)
        agents.append(ProfileAgent(agent_id, package))
    if strict:
        if len(agents) != 4 or set(roles) != FORMAL_ROLE_VALUES or len(set(roles)) != 4:
            raise TeamConfigurationError(
                "formal Profile requires exactly Coordinator, Modeling, Protocol, and Acceptance"
            )
        expected_ids = set(FORMAL_ROLE_VALUES)
        if ids != expected_ids:
            raise TeamConfigurationError("formal Profile Agent IDs must match the four role IDs")
    elif multi_slice:
        # R3.0-002 non-formal branch, relaxed inclusively by R3.0-006 M2: the
        # closed Profile registration now excludes only the formal Profile
        # registry (cross-wire guard); any other Profile loads when it carries
        # each core modeling role exactly once.  Extra roles (future dynamic
        # Agents) are admitted as long as their role names stay in
        # ROLE_VALUES, and only the core-role Agents keep the agent_id == role
        # identity requirement.  The formal branch above is byte-unchanged.
        if profile_id in _FORMAL_PROFILE_IDS:
            raise TeamConfigurationError("multi-slice Profile is not registered")
        role_set = set(roles)
        if len(roles) != len(role_set) or not MULTI_SLICE_ROLE_VALUES <= role_set:
            raise TeamConfigurationError(
                "multi-slice Profile requires exactly one Coordinator, Modeling, and Protocol"
            )
        if any(
            agent.agent_id != agent.package.role
            for agent in agents
            if agent.package.role in MULTI_SLICE_ROLE_VALUES
        ):
            raise TeamConfigurationError(
                "multi-slice Profile core Agent IDs must match the role IDs"
            )
    elif roles.count("coordinator") != 1 or roles.count("protocol") != 1:
        raise TeamConfigurationError(
            "Profile requires exactly one Coordinator and Protocol"
        )
    edges: set[tuple[str, str]] = set()
    raw_edges = data["communication"]
    if not isinstance(raw_edges, list):
        raise TeamConfigurationError("communication must be a list")
    for item in raw_edges:
        if (
            not isinstance(item, dict)
            or set(item) != {"from", "to"}
            or not isinstance(item["to"], list)
        ):
            raise TeamConfigurationError("communication edge is invalid")
        sender = item["from"]
        if sender not in ids:
            raise TeamConfigurationError("communication sender is unknown")
        for recipient in item["to"]:
            if (
                recipient not in ids
                or recipient == sender
                or (sender, recipient) in edges
            ):
                raise TeamConfigurationError(
                    "communication has an unknown, self, or duplicate edge"
                )
            edges.add((sender, recipient))
    if not isinstance(data["parameters"], dict):
        raise TeamConfigurationError("parameters must be an object")
    if _CANDIDATE_PROGRESS_TIMEOUT_PARAMETER in data["parameters"]:
        if profile_id not in _FORMAL_PROFILE_IDS:
            raise TeamConfigurationError(
                "candidate progress timeout is restricted to the formal Profile"
            )
        _validate_candidate_progress_timeout(
            data["parameters"][_CANDIDATE_PROGRESS_TIMEOUT_PARAMETER]
        )
    if _CANDIDATE_REDRIVE_LIMIT_PARAMETER in data["parameters"]:
        if profile_id not in _FORMAL_PROFILE_IDS:
            raise TeamConfigurationError(
                "candidate redrive limit is restricted to the formal Profile"
            )
        _validate_positive_int_parameter(
            _CANDIDATE_REDRIVE_LIMIT_PARAMETER,
            data["parameters"][_CANDIDATE_REDRIVE_LIMIT_PARAMETER],
        )
    if _FEEDBACK_ESCALATION_REPEAT_PARAMETER in data["parameters"]:
        if profile_id not in _FORMAL_PROFILE_IDS:
            raise TeamConfigurationError(
                "feedback escalation repeat is restricted to the formal Profile"
            )
        _validate_positive_int_parameter(
            _FEEDBACK_ESCALATION_REPEAT_PARAMETER,
            data["parameters"][_FEEDBACK_ESCALATION_REPEAT_PARAMETER],
        )
    if _RUN_FALLBACK_TIMEOUT_PARAMETER in data["parameters"]:
        if profile_id not in _RUN_FALLBACK_TIMEOUT_PROFILE_IDS:
            raise TeamConfigurationError(
                "run fallback timeout is restricted to the formal Profile"
            )
        _validate_run_fallback_timeout(
            data["parameters"][_RUN_FALLBACK_TIMEOUT_PARAMETER]
        )
    if strict:
        required_edges = {
            ("coordinator", "modeling"),
            ("coordinator", "protocol"),
            ("coordinator", "acceptance"),
            ("modeling", "coordinator"),
            ("modeling", "protocol"),
            ("protocol", "coordinator"),
            ("protocol", "modeling"),
            ("acceptance", "coordinator"),
        }
        if edges != required_edges:
            raise TeamConfigurationError("formal Profile communication graph drift")
    if multi_slice:
        # R3.0-006 M2 inclusive edge check: the core-role edge set is a
        # required subset; edges of extra roles no longer break the graph.
        required_edges = {
            ("coordinator", "modeling"),
            ("coordinator", "protocol"),
            ("modeling", "coordinator"),
            ("modeling", "protocol"),
            ("protocol", "coordinator"),
            ("protocol", "modeling"),
        }
        if not required_edges <= edges:
            raise TeamConfigurationError("multi-slice Profile communication graph drift")
    parameter_binding = data["parameters"].get("expected_matrix_binding")
    top_level_binding = data.get("expected_matrix_binding")
    if parameter_binding is not None and top_level_binding is not None and parameter_binding != top_level_binding:
        raise TeamConfigurationError("Profile expected_matrix_binding is duplicated with drift")
    expected_matrix_binding = _expected_matrix_binding(
        top_level_binding if top_level_binding is not None else parameter_binding,
        location="Profile",
    )
    modeling = next(
        (agent.package for agent in agents if agent.package.role == "modeling"), None
    )
    if modeling is not None:
        skill_text = "\n".join(
            path.read_text(encoding="utf-8") for path in modeling.required_skills
        )
        instructions_text = modeling.instructions_path.read_text(encoding="utf-8")
        if "Protocol" not in skill_text or "Protocol" not in instructions_text:
            raise TeamConfigurationError(
                "Modeling role must explicitly defer platform calls to Protocol"
            )
    return TeamProfile(
        profile_id,
        "codex",
        tuple(agents),
        frozenset(edges),
        data["parameters"],
        expected_matrix_binding,
    )


def _load_v2_source(
    root: Path, raw: object, seen_paths: set[Path], allowed_roles: set[str]
) -> TaskSource:
    if not isinstance(raw, dict) or set(raw) != {"path", "classification", "roles"}:
        raise TeamConfigurationError("v2 source fields drift from schema")
    source = _repo_path(root, raw["path"], field="role_sources.path")
    relative = source.relative_to(root)
    if source in seen_paths:
        raise TeamConfigurationError("v2 Task duplicates a source path")
    seen_paths.add(source)
    classification = raw["classification"]
    roles = raw["roles"]
    if classification not in SOURCE_CLASSIFICATIONS:
        raise TeamConfigurationError("v2 Task source classification is invalid")
    if not isinstance(roles, list) or not roles or any(role not in allowed_roles for role in roles):
        raise TeamConfigurationError("v2 Task source roles are invalid")
    if len(set(roles)) != len(roles):
        raise TeamConfigurationError("v2 Task source duplicates a role")
    normalized = relative.as_posix().lower()
    forbidden = (
        "tester-only",
        "runtime/",
        "delivery/",
        "workspaces/",
        "requirements/",
        "historical",
        "secret",
    )
    if any(token in normalized for token in forbidden):
        raise TeamConfigurationError("v2 Task source is not Agent-visible")
    return TaskSource(source, relative, classification, frozenset(roles))


def load_task(
    path: Path, *, root: Path | None = None, allowed_roles: set[str] | None = None
) -> TeamTask:
    root = root or repository_root()
    data = _yaml(path)
    _reject_forbidden(data, location="Task")
    v1_fields = {
        "schema_version",
        "task_id",
        "objective",
        "allowed_sources",
        "expected_terminal_evidence",
        "prohibitions",
    }
    v2_fields = {
        "schema_version",
        "task_id",
        "objective",
        "role_sources",
        "protocol_tools",
        "expected_terminal_evidence",
        "retain_nonempty",
        "semantic_start_evidence",
    }
    v2_fields_with_binding = v2_fields | {"expected_matrix_binding"}
    v2_fields_with_parameters = v2_fields | {"parameters"}
    v2_fields_with_parameters_with_binding = v2_fields_with_parameters | {
        "expected_matrix_binding"
    }
    version = data.get("schema_version")
    if version not in {1, 2} or not isinstance(data.get("objective"), str):
        raise TeamConfigurationError("Task schema is invalid")
    if version == 1:
        if set(data) != v1_fields:
            raise TeamConfigurationError("Task fields drift from schema")
        sources = data["allowed_sources"]
        prohibited = data["prohibitions"]
        evidence = data["expected_terminal_evidence"]
        if (
            not isinstance(sources, list)
            or not isinstance(prohibited, list)
            or not isinstance(evidence, list)
        ):
            raise TeamConfigurationError("Task lists are invalid")
        blocked = " ".join(str(item).lower() for item in prohibited)
        if "modeling batch" not in blocked or "modeling item" not in blocked:
            raise TeamConfigurationError(
                "R2.3-001 Task must prohibit Modeling Items and Modeling Batch"
            )
        return TeamTask(
            _safe_id(data["task_id"], "task_id"),
            data["objective"],
            tuple(_repo_path(root, item, field="allowed_sources") for item in sources),
            tuple(str(item) for item in evidence),
        )
    if (
        set(data)
        != v2_fields
        and set(data) != v2_fields_with_binding
        and set(data) != v2_fields_with_parameters
        and set(data) != v2_fields_with_parameters_with_binding
    ):
        raise TeamConfigurationError("v2 Task fields drift from schema")
    # R3.0-002 (c): the optional, closed ``parameters`` key set.  Nothing else
    # may ride on this extension, and every pre-existing v2 Task (no
    # ``parameters`` key) keeps its exact previous validation behavior.
    raw_parameters = data.get("parameters")
    parameters: dict[str, Any] = {}
    if raw_parameters is not None:
        if (
            not isinstance(raw_parameters, dict)
            or not raw_parameters
            or set(raw_parameters) - _TASK_PARAMETER_NAMES
        ):
            raise TeamConfigurationError("v2 Task parameters are invalid")
        for parameter_name in sorted(_TASK_PARAMETER_NAMES & set(raw_parameters)):
            if parameter_name == ACCEPTANCE_TARGET_PARAMETER:
                # The only non-boolean member of the closed set; validated as
                # a string enum below so the boolean check never fires for it.
                continue
            if not isinstance(raw_parameters[parameter_name], bool):
                raise TeamConfigurationError("v2 Task parameters are invalid")
        parameters = dict(raw_parameters)
        if ACCEPTANCE_TARGET_PARAMETER in parameters and (
            not isinstance(parameters[ACCEPTANCE_TARGET_PARAMETER], str)
            or parameters[ACCEPTANCE_TARGET_PARAMETER] not in ACCEPTANCE_TARGET_VALUES
        ):
            raise TeamConfigurationError("v2 Task acceptance_target is invalid")
        if (
            parameters.get(ACCEPTANCE_TARGET_PARAMETER) == ACCEPTANCE_TARGET_CQ_SEMANTIC
            and parameters.get(COMPETENCY_QUESTION_ACCEPTANCE_PARAMETER) is not True
        ):
            # R3.0-012 (design §2.2): ``cq_semantic`` only applies to a Task that
            # already selected the R3.0-011 competency-question flow; it cannot
            # retrofit an unrelated v3 Task onto the CQ acceptance contract.
            raise TeamConfigurationError(
                "cq_selector_incompatible: acceptance_target cq_semantic requires "
                "competency_question_acceptance"
            )
        if parameters.get(STAGED_MODELING_DECISIONS_PARAMETER) is True and parameters.get(
            MULTI_SLICE_TASK_PARAMETER
        ) is not True:
            # R3.0-008B staged decisions ride on the R3.0-002 multi-slice
            # workflow; the dependency is a specific, typed configuration
            # error rather than a generic parameter rejection.
            raise TeamConfigurationError("staged_modeling_decisions requires multi_slice_workflow")
        if parameters.get(UNIFIED_GRAPH_TASK_PARAMETER) is True:
            # R3.0-009: the unified semantic graph flow materializes through the
            # staged decisions path, so it needs both underlying capabilities.
            missing = [
                name
                for name in (MULTI_SLICE_TASK_PARAMETER, STAGED_MODELING_DECISIONS_PARAMETER)
                if parameters.get(name) is not True
            ]
            if missing:
                raise TeamConfigurationError(
                    "unified_semantic_graph requires " + " and ".join(sorted(missing))
                )
        if parameters.get(COMPETENCY_QUESTION_ACCEPTANCE_PARAMETER) is True:
            # R3.0-011: competency-question acceptance rides on the staged
            # multi-slice workflow (design §3.1).  The dependency is a typed,
            # narrow selector error, not a generic parameter rejection.
            missing = [
                name
                for name in (MULTI_SLICE_TASK_PARAMETER, STAGED_MODELING_DECISIONS_PARAMETER)
                if parameters.get(name) is not True
            ]
            if missing:
                raise TeamConfigurationError(
                    "cq_selector_incompatible: competency_question_acceptance requires "
                    + " and ".join(sorted(missing))
                )
        if parameters.get(MODELING_CHECKPOINTS_PARAMETER) is True:
            # R3.0-015 S1 (design §9): checkpoints save from the staged
            # unified v3 path; the three underlying selectors must all be on.
            missing = [
                name
                for name in (
                    MULTI_SLICE_TASK_PARAMETER,
                    STAGED_MODELING_DECISIONS_PARAMETER,
                    UNIFIED_GRAPH_TASK_PARAMETER,
                )
                if parameters.get(name) is not True
            ]
            if missing:
                raise TeamConfigurationError(
                    "modeling_checkpoints requires " + " and ".join(sorted(missing))
                )
    raw_sources = data["role_sources"]
    tools = data["protocol_tools"]
    evidence = data["expected_terminal_evidence"]
    start_evidence = data["semantic_start_evidence"]
    if not all(isinstance(value, list) for value in (raw_sources, tools, evidence, start_evidence)):
        raise TeamConfigurationError("v2 Task lists are invalid")
    seen_paths: set[Path] = set()
    permitted_roles = allowed_roles or ADMITTED_ROLE_VALUES
    sources = tuple(
        _load_v2_source(root, value, seen_paths, permitted_roles) for value in raw_sources
    )
    if not sources:
        raise TeamConfigurationError("v2 Task requires role-private sources")
    if parameters.get(MULTI_SLICE_TASK_PARAMETER) is True:
        # R3.0-002: the multi-slice task adds the protection-set tools.
        allowed_tools = SAFE_PROTOCOL_TOOLS_R30002
    elif data.get("task_id") == "r2-3-003-existing-scope-incremental":
        allowed_tools = SAFE_PROTOCOL_TOOLS_R23003
    else:
        allowed_tools = SAFE_PROTOCOL_TOOLS
    if not all(isinstance(tool, str) and tool in allowed_tools for tool in tools):
        raise TeamConfigurationError("v2 Task Protocol tool is not permitted")
    if len(set(tools)) != len(tools) or not tools:
        raise TeamConfigurationError("v2 Task Protocol tools must be unique and non-empty")
    if not isinstance(data["retain_nonempty"], bool):
        raise TeamConfigurationError("v2 Task retention policy is invalid")
    expected_matrix_binding = _expected_matrix_binding(
        data.get("expected_matrix_binding"), location="Task"
    )
    return TeamTask(
        _safe_id(data["task_id"], "task_id"),
        data["objective"],
        tuple(source.path for source in sources),
        tuple(str(item) for item in evidence),
        schema_version=2,
        role_sources=sources,
        protocol_tools=tuple(tools),
        retain_nonempty=data["retain_nonempty"],
        semantic_start_evidence=tuple(str(item) for item in start_evidence),
        expected_matrix_binding=expected_matrix_binding,
        parameters=parameters,
    )


def load_team_configuration(
    profile_path: Path,
    task_path: Path,
    *,
    root: Path | None = None,
    strict: bool = False,
) -> TeamConfiguration:
    profile = load_profile(profile_path, root=root, strict=strict)
    task = load_task(
        task_path,
        root=root,
        allowed_roles={agent.package.role for agent in profile.agents},
    )
    if (
        profile.expected_matrix_binding is not None
        and task.expected_matrix_binding is not None
        and profile.expected_matrix_binding != task.expected_matrix_binding
    ):
        raise TeamConfigurationError("Profile and Task expected_matrix_binding drift")
    return TeamConfiguration(
        profile,
        task,
    )


def load_formal_team_configuration(
    profile_path: Path, task_path: Path, *, root: Path | None = None
) -> TeamConfiguration:
    """Load only the exact four-role R2.3-005 formal workflow.

    Keeping this explicit avoids accidentally widening every historical P2/P2a
    fixture while making the new Runner entrypoint fail closed before any scope
    or Agent startup.
    """
    return load_team_configuration(profile_path, task_path, root=root, strict=True)


def task_declares_multi_slice_workflow(task_path: Path) -> bool:
    """Peek the frozen Task YAML for the R3.0-002 multi-slice parameter.

    This dispatch peek is the only place the CLI ``validate``/run loader and
    ``TeamRunner.prepare`` need to decide between the strict formal loader and
    the non-formal multi-slice loader (design increment 6(b)).  It is a hint,
    not a validator: an unreadable or malformed Task peeks False and the
    subsequently chosen loader produces the authoritative typed error, so the
    peek never changes pre-existing failure behavior.
    """

    try:
        data = _yaml(task_path)
    except TeamConfigurationError:
        return False
    if not isinstance(data.get("schema_version"), int) or data.get("schema_version") != 2:
        return False
    parameters = data.get("parameters")
    return (
        isinstance(parameters, dict)
        and parameters.get(MULTI_SLICE_TASK_PARAMETER) is True
    )


def task_declares_competency_question_acceptance(task_path: Path) -> bool:
    """Peek the frozen Task YAML for the R3.0-011 CQ acceptance parameter.

    Same contract as :func:`task_declares_multi_slice_workflow`: a hint for the
    Runner/CLI dispatch, never a validator.  An unreadable or malformed Task
    peeks ``False`` and the chosen loader produces the authoritative error.
    """

    try:
        data = _yaml(task_path)
    except TeamConfigurationError:
        return False
    if not isinstance(data.get("schema_version"), int) or data.get("schema_version") != 2:
        return False
    parameters = data.get("parameters")
    return (
        isinstance(parameters, dict)
        and parameters.get(COMPETENCY_QUESTION_ACCEPTANCE_PARAMETER) is True
    )


def normalize_acceptance_target(parameters: dict[str, Any] | None) -> str:
    """Frozen normalization for the run-contract snapshot (R3.0-012 §2.2).

    Omission is ``full_joint``.  A present-but-invalid value is the same typed
    configuration error ``load_task`` raises, so the snapshot writer can never
    silently re-derive a different scope than the loaded Task declared.
    """

    value = (parameters or {}).get(ACCEPTANCE_TARGET_PARAMETER)
    if value is None:
        return ACCEPTANCE_TARGET_FULL_JOINT
    if not isinstance(value, str) or value not in ACCEPTANCE_TARGET_VALUES:
        raise TeamConfigurationError("v2 Task acceptance_target is invalid")
    return value


def task_declares_cq_semantic_target(task_path: Path) -> bool:
    """Peek the frozen Task YAML for the R3.0-012 ``cq_semantic`` target.

    Same contract as :func:`task_declares_multi_slice_workflow`: a dispatch
    hint, never a validator.  An unreadable or malformed Task peeks ``False``
    and the chosen loader produces the authoritative typed error.
    """

    try:
        data = _yaml(task_path)
    except TeamConfigurationError:
        return False
    if not isinstance(data.get("schema_version"), int) or data.get("schema_version") != 2:
        return False
    parameters = data.get("parameters")
    return (
        isinstance(parameters, dict)
        and parameters.get(ACCEPTANCE_TARGET_PARAMETER) == ACCEPTANCE_TARGET_CQ_SEMANTIC
    )


def load_multi_slice_team_configuration(
    profile_path: Path, task_path: Path, *, root: Path | None = None
) -> TeamConfiguration:
    """Load only the non-formal R3.0-002 three-role multi-slice workflow.

    The strict four-role formal check is unchanged; this explicit branch
    accepts exactly the registered multi-slice Profile paired with a Task that
    declares ``parameters.multi_slice_workflow: true``.
    """

    root = root or repository_root()
    profile = load_profile(profile_path, root=root, multi_slice=True)
    task = load_task(
        task_path,
        root=root,
        allowed_roles={agent.package.role for agent in profile.agents},
    )
    if task.parameters is None or task.parameters.get(MULTI_SLICE_TASK_PARAMETER) is not True:
        raise TeamConfigurationError(
            "multi-slice Profile requires a Task declaring multi_slice_workflow"
        )
    # R3.0-011: the competency-question selector and the CQ Agent must select
    # each other.  A profile that carries the role without the selector, or a
    # selector without exactly one CQ Agent, is a typed selector error; a
    # three-role task/profile pair is unchanged and never requires CQ.
    cq_agents = [
        agent
        for agent in profile.agents
        if agent.package.role == COMPETENCY_QUESTION_ROLE
    ]
    cq_selected = task.parameters.get(COMPETENCY_QUESTION_ACCEPTANCE_PARAMETER) is True
    if cq_selected and len(cq_agents) != 1:
        raise TeamConfigurationError(
            "cq_selector_incompatible: competency_question_acceptance requires exactly one "
            "competency-question Agent in the Profile"
        )
    if cq_agents and not cq_selected:
        raise TeamConfigurationError(
            "cq_selector_incompatible: a competency-question Agent requires "
            "parameters.competency_question_acceptance"
        )
    if (
        profile.expected_matrix_binding is not None
        and task.expected_matrix_binding is not None
        and profile.expected_matrix_binding != task.expected_matrix_binding
    ):
        raise TeamConfigurationError("Profile and Task expected_matrix_binding drift")
    return TeamConfiguration(
        profile,
        task,
    )


def digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
