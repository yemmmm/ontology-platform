"""The small, versioned boundary between Host inputs, semantic work and execution."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from jsonschema import ValidationError, validate

from .results import ResultContractError, decode_json_result

if TYPE_CHECKING:
    from .preflight import ModelBinding

WORKFLOW_VERSION = "p1.1/v1"
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class FrameworkError(ValueError):
    def __init__(self, code: str, *, layer: str = "platform-contract", **detail):
        super().__init__(code)
        self.code = code
        self.layer = layer
        self.recoverable = True
        self.detail = detail

    def as_dict(self) -> dict:
        return {"code": self.code, "layer": self.layer, "recoverable": True, **self.detail}


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def write_json(path: Path, value: object) -> None:
    """A completed receipt must not be confused with a partly written JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def safe_id(value: str) -> str:
    if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
        raise FrameworkError("invalid_identity")
    return value


def bound_project_ref(task, repository):
    if task.get("project_ref"):
        return task["project_ref"]
    row = repository.get("run:" + task["run_id"] + ":project-binding")
    return row["content"]["project_id"] if row else None


def modeling_instructions(task_instructions):
    """Freeze the current method and reusable platform grammar for a new task only."""
    package = Path(__file__).resolve().parents[2]
    instructions = task_instructions
    if not instructions.startswith("# Bounded v5 modeling and self-check"):
        instructions = (
            (package / "instructions/modeling.md").read_text()
            + "\n\nTask-specific instructions:\n"
            + instructions
        )
    if "Technical representation contracts (not business sources):" not in instructions:
        references = package.parent / "references"
        direct = json.loads((references / "r4-3-025-direct-modeling-contract.json").read_text())
        semantics = json.loads((references / "r4-0-012-modeling-contract.json").read_text())
        contract = {
            "change": direct["change"],
            "candidate": direct["candidate"],
            "request_example": direct["fields_only_example"]["request"],
            "relation_request_example": direct["fields_only_example"]["relation_request_template"],
            "semantic_definition": semantics["multiview_semantic_definition"],
        }
        instructions += (
            "\n\nTechnical representation contracts (not business sources):\n"
            + json.dumps(contract, ensure_ascii=False)
        )
    return instructions


def _check_sources(root: Path) -> dict:
    manifest = json.loads((root / "manifest.json").read_text())
    if not isinstance(manifest, dict) or not manifest:
        raise FrameworkError("source_manifest_required")
    for material_id, entry in manifest.items():
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise FrameworkError("material_forbidden", material_id=material_id)
        path = (root / entry["path"]).resolve()
        if not path.is_relative_to(root.resolve()):
            raise FrameworkError("material_forbidden", material_id=material_id)
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise FrameworkError("source_revision_changed", material_id=material_id)
    return manifest


@dataclass(frozen=True)
class TaskBinding:
    root: Path
    data: dict

    @classmethod
    def prepare(cls, task_path: Path, root: Path) -> TaskBinding:
        from .preflight import ModelBinding

        task_path, root = task_path.resolve(), root.resolve()
        if root.exists():
            raise FileExistsError(root)
        task = yaml.safe_load(task_path.read_text())
        required = {
            "schema_version",
            "task_ref",
            "run_id",
            "work_unit_id",
            "objective",
            "materials",
            "model_profile",
            "instructions",
            "authorization",
            "scope",
            "evaluation",
        }
        if (
            not isinstance(task, dict)
            or set(task)
            - {
                "collaboration",
                "shared_memory",
                "work_units",
                "unit_concurrency",
                "work_management",
                "semantic_workspace",
                "project_ref",
                "workspace_ref",
            }
            != required
        ):
            raise FrameworkError("task_schema_mismatch", required=sorted(required))
        if task["schema_version"] != "ontoweave-task/v1":
            raise FrameworkError("task_schema_mismatch")
        for field in ("task_ref", "run_id", "work_unit_id"):
            safe_id(task[field])
        units = task.get("work_units", [])
        unit_ids = [safe_id(unit["unit_id"]) for unit in units]
        if len(set(unit_ids)) != len(unit_ids) or set(unit_ids) & {
            "modeling",
            "acceptance",
            task["work_unit_id"],
        }:
            raise FrameworkError("work_unit_identity_conflict")
        if any(not unit.get("objective") for unit in units):
            raise FrameworkError("work_unit_objective_required")
        if type(task.get("unit_concurrency", 2)) is not int or task.get("unit_concurrency", 2) < 1:
            raise FrameworkError("unit_concurrency_invalid")
        if "collaboration" in task:
            peers = task["collaboration"].get("peers", [])
            if not peers or len({p["agent_id"] for p in peers}) != len(peers):
                raise FrameworkError("team_roster_invalid")
            for peer in peers:
                safe_id(peer["agent_id"])
                if peer["agent_id"] in {"modeling", "acceptance"} or not peer.get("objective"):
                    raise FrameworkError("team_roster_invalid")
        for field in ("objective", "instructions"):
            if not isinstance(task[field], str) or not task[field].strip():
                raise FrameworkError("task_field_required", field=field)
        for field in ("authorization", "scope", "evaluation"):
            if not isinstance(task[field], dict):
                raise FrameworkError("task_field_invalid", field=field)
        authorization = task["authorization"]
        if authorization.get("mode") not in {"usage_only", "amount"}:
            raise FrameworkError("authorization_mode_not_implemented")
        if not authorization.get("reference"):
            raise FrameworkError("authorization_reference_required")
        if authorization["mode"] == "amount":
            if not authorization.get("budget_ref"):
                raise FrameworkError("budget_reference_required")
            authorization["budget_ref"] = str(
                (task_path.parent / authorization["budget_ref"]).resolve()
            )
        if task["scope"].get("mode") not in {"create", "existing"}:
            raise FrameworkError("scope_mode_not_implemented")
        if not task["scope"].get("base_url"):
            raise FrameworkError("platform_url_required")
        evaluation = task["evaluation"]
        if (
            not evaluation.get("freeze_id")
            or not re.fullmatch(r"[a-f0-9]{64}", evaluation.get("sha256", ""))
            or type(evaluation.get("case_count")) is not int
            or evaluation["case_count"] <= 0
        ):
            raise FrameworkError("evaluation_freeze_required")
        materials = (task_path.parent / task["materials"]).resolve()
        profile = (task_path.parent / task["model_profile"]).resolve()
        manifest = _check_sources(materials)
        models = {
            role: asdict(ModelBinding.from_profile(profile, role))
            for role in ("modeling", "acceptance")
        }
        if any(model["provider"] != "glm-direct" for model in models.values()):
            raise FrameworkError("provider_route_not_implemented")
        data = {
            **{
                key: value
                for key, value in task.items()
                if key not in {"materials", "model_profile"}
            },
            "workflow_version": WORKFLOW_VERSION,
            "models": models,
            "profile_sha256": hashlib.sha256(profile.read_bytes()).hexdigest(),
            "source_manifest": manifest,
            "source_manifest_digest": digest(manifest),
        }
        data["instructions"] = modeling_instructions(task["instructions"])
        root.mkdir(parents=True, exist_ok=False, mode=0o700)
        for entry in manifest.values():
            destination = root / "materials" / entry["path"]
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            destination.write_bytes((materials / entry["path"]).read_bytes())
        write_json(root / "materials" / "manifest.json", manifest)
        (root / "model-profile.yaml").write_bytes(profile.read_bytes())
        write_json(root / "binding.json", {"digest": digest(data), "binding": data})
        return cls.load(root)

    @classmethod
    def load(cls, root: Path) -> TaskBinding:
        root = root.resolve()
        envelope = json.loads((root / "binding.json").read_text())
        data = envelope["binding"]
        if envelope["digest"] != digest(data) or data["workflow_version"] != WORKFLOW_VERSION:
            raise FrameworkError("binding_changed_or_incompatible")
        if (
            _check_sources(root / data.get("source_directory", "materials"))
            != data["source_manifest"]
        ):
            raise FrameworkError("source_manifest_changed")
        if (
            hashlib.sha256((root / "model-profile.yaml").read_bytes()).hexdigest()
            != data["profile_sha256"]
        ):
            raise FrameworkError("model_profile_changed")
        return cls(root, data)

    def model(self, role: str) -> ModelBinding:
        from .preflight import ModelBinding

        return ModelBinding(**self.data["models"][role])

    @property
    def materials(self) -> Path:
        return self.root / self.data.get("source_directory", "materials")

    @property
    def identity(self) -> str:
        identity = f"run:{self.data['run_id']}"
        return identity + ":unit:" + self.data["_unit_id"] if self.is_child else identity

    @property
    def is_child(self) -> bool:
        return "_unit_id" in self.data

    @property
    def actor(self) -> str:
        return self.data.get("_unit_id", "modeling")

    @property
    def thread_id(self) -> str:
        identity = self.identity if self.is_child else self.data["run_id"]
        if self.data.get("cycle_id"):
            identity += ":cycle:" + self.data["cycle_id"]
        if self.data.get("work_generation"):
            identity += ":generation:" + str(self.data["work_generation"])
        return identity

    def execution_id(self, local_id: str) -> str:
        return self.data["_unit_id"] + "--" + local_id if self.is_child else local_id

    def for_unit(self, unit_id: str) -> TaskBinding:
        unit = next(unit for unit in self.data["work_units"] if unit["unit_id"] == unit_id)
        return TaskBinding(
            self.root,
            {
                **self.data,
                "_unit_id": unit_id,
                "_parent_work_unit_id": self.data["work_unit_id"],
                "_parent_actor": unit.get("parent_id", "modeling"),
                "work_generation": unit.get("generation", 0),
                "work_unit_id": unit_id,
                "objective": unit["objective"],
                "assigned_material_ids": unit.get("material_ids", []),
                "instructions": self.data["instructions"] + "\n" + unit.get("instructions", ""),
            },
        )

    @property
    def direct_units(self) -> list[dict]:
        return [
            u
            for u in self.data.get("work_units", [])
            if u.get("parent_id", "modeling") == self.actor
        ]


HUMAN_REQUESTS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "question": {"type": "string", "minLength": 1},
            "reason": {"type": "string", "minLength": 1},
            "impact": {"type": "string", "minLength": 1},
        },
        "required": ["question", "reason", "impact"],
    },
}
RESOLVED_REQUESTS_SCHEMA = {
    "type": "array",
    "uniqueItems": True,
    "items": {"type": "string"},
    "description": "Only human HITL request IDs. Team work requests are resolved "
    "with resolve_work_request, never included here.",
}

WORK_RESULT_SCHEMA = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "status": {
            "enum": [
                "proposed",
                "waiting_input",
                "waiting_peer",
                "waiting_children",
                "no_change",
                "recoverable_issue",
            ],
            "description": "proposed: complete changes ready for the Host to apply; waiting_input: "
            "required business input is missing; recoverable_issue: a current technical gap prevents "
            "a complete proposal. Previous errors and pending application/self-check alone do not "
            "prevent status proposed.",
        },
        "candidate": {"type": ["object", "null"]},
        "changes": {"type": ["object", "null"]},
        "ontology_targets": {
            "type": ["object", "null"],
            "additionalProperties": {"type": "string"},
            "description": "change_id to actual authorized ontology_id placement; required for ambiguous multi-Ontology creates.",
        },
        "source_refs": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"material_id": {"type": "string"}, "sha256": {"type": "string"}},
                "required": ["material_id", "sha256"],
            },
        },
        "issues": {"type": "array", "items": {"type": "string"}},
        "consumed_ids": {"type": "array", "uniqueItems": True, "items": {"type": "string"}},
        "human_requests": HUMAN_REQUESTS_SCHEMA,
        "resolved_request_ids": RESOLVED_REQUESTS_SCHEMA,
    },
    "required": ["status", "candidate", "changes", "source_refs", "issues", "consumed_ids"],
}

SELF_CHECK_SCHEMA = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "status": {"enum": ["ready", "revise", "waiting_input"]},
        "issues": {"type": "array", "items": {"type": "string"}},
        "consumed_ids": WORK_RESULT_SCHEMA["properties"]["consumed_ids"],
        "review_units": {
            "type": "array",
            "items": {"type": "string"},
            "uniqueItems": True,
            "description": "Optional ready direct child IDs whose bounded actual-model self-check is needed.",
        },
        "human_requests": HUMAN_REQUESTS_SCHEMA,
        "resolved_request_ids": RESOLVED_REQUESTS_SCHEMA,
    },
    "required": ["status", "issues", "consumed_ids"],
}


def decode_work_result(message: str, manifest: dict, *, require_changes: bool = True) -> dict:
    try:
        result = decode_json_result(message, WORK_RESULT_SCHEMA)
    except ResultContractError as error:
        raise FrameworkError("work_result_invalid", detail=str(error)) from error
    for ref in result["source_refs"]:
        entry = manifest.get(ref["material_id"])
        if entry is None or entry["sha256"] != ref["sha256"]:
            raise FrameworkError("source_reference_mismatch", material_id=ref["material_id"])
    if result["status"] in {"proposed", "no_change"}:
        if (
            result["status"] == "proposed"
            and require_changes
            and (
                not result["changes"]
                or result["changes"].get("schema_version") != "r4-3-025-model-changes/v1"
            )
        ):
            raise FrameworkError(
                "model_changes_required",
                path="/changes/schema_version",
                expected="r4-3-025-model-changes/v1",
                instruction="Return changes as the complete object with exactly schema_version, "
                "candidate_ref and changes; use schema_version, not request_id. "
                "For fields-only changes, candidate and candidate_ref may be null. "
                "Class fields use name, not label. Preserve the original business meaning.",
            )
        if not result["source_refs"]:
            raise FrameworkError("source_references_required")
    elif result["status"] == "recoverable_issue" and not result["issues"]:
        raise FrameworkError("unresolved_reason_required")
    return result


def validate_schema(value: dict, schema: dict) -> None:
    try:
        validate(value, schema)
    except ValidationError as error:
        raise FrameworkError("schema_invalid", path=list(error.absolute_path)) from error


def outbound_tool_names(tools: list[dict], namespace: str = "") -> list[str]:
    """Read both flat and namespaced tool identities from the real Responses wire format."""
    names = []
    for tool in tools:
        name = tool.get("name", (tool.get("function") or {}).get("name"))
        qualified = f"{namespace}__{name}" if namespace else name
        if tool.get("type") == "namespace":
            names.extend(outbound_tool_names(tool["tools"], qualified))
        else:
            names.append(qualified)
    return names
