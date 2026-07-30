"""Runtime-neutral Profile, Package, and Task contracts for R2.3-001."""

from __future__ import annotations

import hashlib
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


@dataclass(frozen=True)
class TeamTask:
    task_id: str
    objective: str
    allowed_sources: tuple[Path, ...]
    expected_terminal_evidence: tuple[str, ...]


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
    resolved = (root / candidate).resolve()
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
    if role not in {"coordinator", "modeling", "protocol", "source-specialist"}:
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
    if role != "protocol" and platform != "none":
        raise TeamConfigurationError(
            "only Protocol may have platform permission in R2.3-001"
        )
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
    if not isinstance(skills, list) or not skills:
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


def load_profile(path: Path, *, root: Path | None = None) -> TeamProfile:
    root = root or repository_root()
    data = _yaml(path)
    _reject_forbidden(data, location="Profile")
    if set(data) != {
        "schema_version",
        "profile_id",
        "runtime",
        "agents",
        "communication",
        "parameters",
    }:
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
    if roles.count("coordinator") != 1 or roles.count("protocol") != 1:
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
        profile_id, "codex", tuple(agents), frozenset(edges), data["parameters"]
    )


def load_task(path: Path, *, root: Path | None = None) -> TeamTask:
    root = root or repository_root()
    data = _yaml(path)
    _reject_forbidden(data, location="Task")
    if set(data) != {
        "schema_version",
        "task_id",
        "objective",
        "allowed_sources",
        "expected_terminal_evidence",
        "prohibitions",
    }:
        raise TeamConfigurationError("Task fields drift from schema")
    if data["schema_version"] != 1 or not isinstance(data["objective"], str):
        raise TeamConfigurationError("Task schema is invalid")
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


def load_team_configuration(
    profile_path: Path, task_path: Path, *, root: Path | None = None
) -> TeamConfiguration:
    return TeamConfiguration(
        load_profile(profile_path, root=root), load_task(task_path, root=root)
    )


def digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
