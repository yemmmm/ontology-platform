"""Deterministic input and base-package checks for the offline M7 scenario."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


SCENARIO_ROOT = Path(__file__).resolve().parent
AGENT_INPUT = SCENARIO_ROOT / "agent-input"
BASE_SLICE = SCENARIO_ROOT / "base-slice"
HOST_ONLY = SCENARIO_ROOT / "host-only"
CONTRACT_VERSION = "m7-contract-v4-recovery"
SEAL_TOOL = "m7-authoring-seal-v4-recovery"
SEALED_PACKAGE_KEYS = {
    "schema_version",
    "contract_version",
    "input_manifest_sha256",
    "base_manifest_sha256",
    "public_role_bindings",
    "principal",
    "invalid_candidate",
    "principal_candidate_sha256",
    "invalid_candidate_sha256",
    "resource_roles",
    "edge_assertions",
    "closed_snapshot_absence_assertions",
    "cq_claims",
    "seal",
}
RUNTIME_ID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.I
)
FORBIDDEN_VISIBLE_TEXT = (
    "answer-contract-v1",
    "acceptance-contract",
    "mutation-contract",
    "expected cq",
    "hidden answer",
    "there are three",
    "three gaps",
)


class ContractError(RuntimeError):
    """A frozen M7 artifact or visibility invariant was violated."""


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_hash(path: Path) -> str:
    return hashlib.sha256(canonical_json(json.loads(path.read_text(encoding="utf-8")))).hexdigest()


def sealed_envelope_hash(package: dict[str, Any]) -> str:
    """Hash the canonical envelope excluding its deterministic sealing receipt."""
    return hashlib.sha256(canonical_json({key: value for key, value in package.items() if key != "seal"})).hexdigest()


def verify_manifest(root: Path, manifest_name: str = "manifest.json") -> dict[str, Any]:
    """Require exact file membership and content hashes below a frozen root."""
    manifest_path = root / manifest_name
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise ContractError("manifest must declare non-empty files")
    declared = {entry.get("path") for entry in entries if isinstance(entry, dict)}
    actual = {
        item.relative_to(root).as_posix()
        for item in root.rglob("*")
        if item.is_file() and item != manifest_path
    }
    if declared != actual or len(declared) != len(entries):
        raise ContractError("frozen file set differs from manifest")
    for entry in entries:
        relative, expected = entry.get("path"), entry.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise ContractError("manifest entry lacks path or sha256")
        candidate = (root / relative).resolve()
        if root.resolve() not in candidate.parents or not candidate.is_file():
            raise ContractError(f"manifest path escapes root: {relative}")
        if sha256(candidate) != expected:
            raise ContractError(f"frozen hash mismatch: {relative}")
    return manifest


def verify_agent_input() -> dict[str, Any]:
    manifest = verify_manifest(AGENT_INPUT)
    for entry in manifest["files"]:
        relative = entry["path"]
        if relative.startswith(("../", "host-only/", "base-slice/")):
            raise ContractError("Agent-visible manifest exposes a hidden root")
        text = (AGENT_INPUT / relative).read_text(encoding="utf-8").lower()
        if any(marker in text for marker in FORBIDDEN_VISIBLE_TEXT):
            raise ContractError(f"Agent-visible answer leak: {relative}")
    return manifest


def verify_base_slice() -> dict[str, Any]:
    manifest = verify_manifest(BASE_SLICE)
    package = json.loads((BASE_SLICE / "semantic-package.json").read_text(encoding="utf-8"))
    if package.get("schema_version") != 1 or package.get("scope") != "accepted-base-slice":
        raise ContractError("base package has an unsupported schema or scope")
    if package.get("contract_version") != CONTRACT_VERSION:
        raise ContractError("base package contract version drift")
    items = package.get("items")
    if not isinstance(items, list) or not items:
        raise ContractError("base package must contain deterministic items")
    if any(RUNTIME_ID.fullmatch(value) for value in _strings(package)):
        raise ContractError("base package contains a historical runtime ID")
    return manifest


def verify_host_only() -> dict[str, Any]:
    """Verify the hidden answer, acceptance and mutation contracts before a run."""
    manifest = verify_manifest(HOST_ONLY)
    for entry in manifest["files"]:
        value = json.loads((HOST_ONLY / entry["path"]).read_text(encoding="utf-8"))
        if value.get("contract_version") != CONTRACT_VERSION:
            raise ContractError(f"host-only contract version drift: {entry['path']}")
    return manifest


def validate_public_resource_map(value: object) -> dict[str, dict[str, str]]:
    if not isinstance(value, dict) or not value:
        raise ContractError("public resource map must be a non-empty object")
    result: dict[str, dict[str, str]] = {}
    for role, resource in value.items():
        if not isinstance(role, str) or not role or not isinstance(resource, dict):
            raise ContractError("public resource map contains an invalid role")
        resource_id, resource_iri = resource.get("resource_id"), resource.get("resource_iri")
        if not isinstance(resource_id, str) or not resource_id.strip():
            raise ContractError(f"public role {role} lacks resource_id")
        if not isinstance(resource_iri, str) or not resource_iri.startswith(("http://", "https://")):
            raise ContractError(f"public role {role} lacks resource_iri")
        if set(resource) != {"resource_id", "resource_iri"}:
            raise ContractError(f"public role {role} has unsupported fields")
        result[role] = {"resource_id": resource_id, "resource_iri": resource_iri}
    return result


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for child in value for item in _strings(child)]
    if isinstance(value, dict):
        return [item for child in value.values() for item in _strings(child)]
    return []
