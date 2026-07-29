#!/usr/bin/env python3
"""Deterministically seal the one Agent-authored M7 package or prove the local L0 runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import sys
from typing import Any


CONTRACT_VERSION = "m7-contract-v4-recovery"
SEAL_TOOL = "m7-authoring-seal-v4-recovery"
L0_RUNTIME_VERSION = "m7-l0-runtime-v1"
L0_COMMAND = "./seal_semantic_package.py --runtime-check --agent-visible ."
ITEM_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,127}$")
SEMANTIC_KEY = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
ITEM_KEYS = {
    "client_item_id", "command_kind", "payload", "depends_on", "evidence_reference_ids", "evidence", "rationale", "competency_question_ids"
}
ALLOWED_PAYLOADS = {
    "create_class": ({"name"}, {"name", "description", "aliases", "parent_class_ids", "external_mappings"}),
    "create_relation_type": ({"name", "source_class_id", "target_class_id"}, {"name", "source_class_id", "target_class_id", "description", "symmetric", "transitive", "scope_policy", "status"}),
    "create_entity": ({"class_iri_or_legacy_id", "label"}, {"class_iri_or_legacy_id", "label", "aliases", "properties"}),
    "create_relation": ({"source_entity_iri", "relation_type_iri", "target_entity_iri"}, {"source_entity_iri", "relation_type_iri", "target_entity_iri"}),
    "create_shape": ({"target_class_id", "constraints"}, {"target_class_id", "constraints"}),
}


class SealError(RuntimeError):
    pass


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SealError(f"{path.name} is missing or invalid JSON") from exc
    if not isinstance(value, dict):
        raise SealError(f"{path.name} must be an object")
    return value


def _item_refs(value: Any) -> set[str]:
    if isinstance(value, dict):
        if set(value) == {"item_ref"}:
            ref = value["item_ref"]
            if not isinstance(ref, dict) or set(ref) != {"client_item_id", "output"}:
                raise SealError("item_ref must contain only client_item_id and output")
            item_id, output = ref["client_item_id"], ref["output"]
            if not isinstance(item_id, str) or output not in {"resource_id", "resource_iri"}:
                raise SealError("item_ref has an invalid client_item_id or output")
            return {item_id}
        return set().union(*(_item_refs(child) for child in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(_item_refs(child) for child in value)) if value else set()
    return set()


def _validate_reference(value: Any, *, expected_output: str, public_values: set[str], seen: set[str]) -> None:
    if isinstance(value, dict) and set(value) == {"item_ref"}:
        ref = value["item_ref"]
        if ref.get("output") != expected_output or ref.get("client_item_id") not in seen:
            raise SealError("item_ref must use the expected representation and an earlier item")
        return
    if not isinstance(value, str) or value not in public_values:
        raise SealError("cross-batch reference is not an exact public run-manifest value")


def _normalize_item(raw: Any, public_map: dict[str, dict[str, str]], seen: set[str]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise SealError("Modeling Item must be an object")
    unknown = set(raw) - ITEM_KEYS
    if unknown or not {"client_item_id", "command_kind", "payload"} <= set(raw):
        raise SealError("Modeling Item has unsupported or missing fields")
    item = {"depends_on": [], "evidence_reference_ids": [], "evidence": [], "rationale": None, "competency_question_ids": [], **raw}
    item_id, command, payload = item["client_item_id"], item["command_kind"], item["payload"]
    if not isinstance(item_id, str) or not ITEM_ID.fullmatch(item_id) or item_id in seen:
        raise SealError("client_item_id must be unique lowercase kebab-case")
    if command not in ALLOWED_PAYLOADS or not isinstance(payload, dict):
        raise SealError("command_kind or payload is not allowed by the visible authoring contract")
    required, allowed = ALLOWED_PAYLOADS[command]
    if not required <= set(payload) or set(payload) - allowed:
        raise SealError("payload does not match the visible command schema")
    for field in ("depends_on", "evidence_reference_ids", "competency_question_ids"):
        if not isinstance(item[field], list) or not all(isinstance(value, str) and value for value in item[field]):
            raise SealError(f"{field} must be an array of non-empty strings")
    if item["evidence_reference_ids"] or item["competency_question_ids"]:
        raise SealError("this v4 run manifest requires empty Evidence and CompetencyQuestion ID arrays")
    if item["rationale"] is not None and not isinstance(item["rationale"], str):
        raise SealError("rationale must be a string or null")
    if not isinstance(item["evidence"], list) or any(not isinstance(value, dict) or set(value) != {"document_name", "excerpt"} or not all(isinstance(value.get(key), str) and value[key] for key in value) for value in item["evidence"]):
        raise SealError("evidence entries must contain only document_name and excerpt strings")
    ids = {resource["resource_id"] for resource in public_map.values()}
    iris = {resource["resource_iri"] for resource in public_map.values()}
    if command == "create_class":
        for value in payload.get("parent_class_ids", []):
            _validate_reference(value, expected_output="resource_id", public_values=ids, seen=seen)
    elif command == "create_relation_type":
        for field in ("source_class_id", "target_class_id"):
            _validate_reference(payload[field], expected_output="resource_id", public_values=ids, seen=seen)
    elif command == "create_entity":
        _validate_reference(payload["class_iri_or_legacy_id"], expected_output="resource_iri", public_values=iris, seen=seen)
    elif command == "create_relation":
        for field in ("source_entity_iri", "relation_type_iri", "target_entity_iri"):
            _validate_reference(payload[field], expected_output="resource_iri", public_values=iris, seen=seen)
    else:
        _validate_reference(payload["target_class_id"], expected_output="resource_id", public_values=ids, seen=seen)
        if not isinstance(payload["constraints"], list):
            raise SealError("create_shape constraints must be an array")
        for constraint in payload["constraints"]:
            if not isinstance(constraint, dict) or "path_id" not in constraint or set(constraint) - {"path_id", "min_count", "max_count", "datatype", "pattern", "description", "enum_values"}:
                raise SealError("create_shape constraint does not match the visible schema")
            _validate_reference(constraint["path_id"], expected_output="resource_id", public_values=ids, seen=seen)
    dependencies = sorted(_item_refs(payload))
    if item["depends_on"] != dependencies:
        raise SealError("depends_on must exactly declare payload item_ref dependencies")
    return {key: item[key] for key in sorted(ITEM_KEYS)}


def _absolute_iri(value: object) -> bool:
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def _validate_literal(value: object) -> None:
    if not isinstance(value, dict) or set(value) - {"value", "datatype", "language"}:
        raise SealError("literal has unsupported fields")
    if not isinstance(value.get("value"), str):
        raise SealError("literal value must be a string")
    datatype, language = value.get("datatype"), value.get("language")
    if datatype is not None and not _absolute_iri(datatype):
        raise SealError("literal datatype must be an absolute IRI")
    if language is not None and (not isinstance(language, str) or not re.fullmatch(r"[A-Za-z]{1,8}(?:-[A-Za-z0-9]{1,8})*", language)):
        raise SealError("literal language is invalid")
    if datatype is not None and language is not None:
        raise SealError("literal cannot use datatype and language together")


def _validate_v3_proof(raw: dict[str, Any], principal: dict[str, Any], public_map: dict[str, dict[str, str]]) -> dict[str, Any]:
    roles = raw.get("resource_roles")
    assertions = raw.get("edge_assertions")
    absences = raw.get("closed_snapshot_absence_assertions", [])
    claims = raw.get("cq_claims")
    if not all(isinstance(value, list) for value in (roles, assertions, absences, claims)):
        raise SealError("v3 proof fields must be arrays")
    items = {item["client_item_id"]: item["command_kind"] for item in principal["items"]}
    role_names: set[str] = set()
    semantic_keys: set[str] = set()
    for entry in roles:
        if not isinstance(entry, dict) or set(entry) != {"role", "semantic_key", "source"}:
            raise SealError("resource_role has an invalid shape")
        role, semantic_key, source = entry.get("role"), entry.get("semantic_key"), entry.get("source")
        if not isinstance(role, str) or not ITEM_ID.fullmatch(role) or role in role_names or not isinstance(semantic_key, str) or not SEMANTIC_KEY.fullmatch(semantic_key) or semantic_key in semantic_keys or not isinstance(source, dict):
            raise SealError("resource_role must have a unique role and source")
        if set(source) == {"public_role"}:
            if source["public_role"] not in public_map:
                raise SealError("resource_role references an unknown public role")
        elif set(source) == {"client_item_id"}:
            item_id = source["client_item_id"]
            if item_id not in items or items[item_id] not in {"create_class", "create_relation_type", "create_shape", "create_entity"}:
                raise SealError("resource_role must name an output-capable create item")
        else:
            raise SealError("resource_role source must be public_role or client_item_id")
        role_names.add(role)
        semantic_keys.add(semantic_key)

    assertion_ids: set[str] = set()
    def check_assertion(entry: object, *, absence: bool) -> None:
        if not isinstance(entry, dict) or set(entry) != {"id", "subject_role", "predicate", "object"}:
            raise SealError("edge assertion has an invalid shape")
        assertion_id, subject, predicate, operand = entry.get("id"), entry.get("subject_role"), entry.get("predicate"), entry.get("object")
        if not isinstance(assertion_id, str) or not ITEM_ID.fullmatch(assertion_id) or assertion_id in assertion_ids:
            raise SealError("edge assertion ID must be unique")
        if not isinstance(subject, str) or subject not in role_names or not isinstance(predicate, dict) or not isinstance(operand, dict):
            raise SealError("edge assertion has an unresolved role")
        if set(predicate) == {"role"}:
            if predicate["role"] not in role_names:
                raise SealError("predicate role is unresolved")
        elif set(predicate) != {"iri"} or not _absolute_iri(predicate.get("iri")):
            raise SealError("predicate must be a role or absolute IRI")
        if set(operand) == {"role"}:
            if operand["role"] not in role_names:
                raise SealError("object role is unresolved")
        elif set(operand) == {"literal"}:
            _validate_literal(operand["literal"])
        else:
            raise SealError("object must be a role or literal")
        if not absence:
            assertion_ids.add(assertion_id)

    for entry in assertions:
        check_assertion(entry, absence=False)
    for entry in absences:
        check_assertion(entry, absence=True)
    allowed_claim_kinds = {"connected_typed_path", "certain_available", "certain_unavailable", "explicit_unknown", "dependency_path"}
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != {"id", "kind", "assertion_ids", "bindings"}:
            raise SealError("cq_claim has an invalid shape")
        if not isinstance(claim.get("id"), str) or not ITEM_ID.fullmatch(claim["id"]) or claim.get("kind") not in allowed_claim_kinds:
            raise SealError("cq_claim ID is invalid")
        ids = claim.get("assertion_ids")
        if not isinstance(ids, list) or not ids or len(ids) != len(set(ids)) or not all(item in assertion_ids for item in ids):
            raise SealError("cq_claim must cite positive assertions only")
        _validate_claim_bindings(claim["kind"], claim.get("bindings"), role_names)
    return {"resource_roles": roles, "edge_assertions": assertions, "closed_snapshot_absence_assertions": absences, "cq_claims": claims}


def _validate_role_sequence(value: object, role_names: set[str]) -> None:
    if not isinstance(value, list) or len(value) < 2 or not all(isinstance(role, str) and role in role_names for role in value):
        raise SealError("claim path must be an ordered sequence of declared roles")


def _validate_claim_bindings(kind: str, bindings: object, role_names: set[str]) -> None:
    if not isinstance(bindings, dict):
        raise SealError("cq_claim bindings must be an object")
    if kind == "connected_typed_path":
        if set(bindings) != {"paths"} or not isinstance(bindings["paths"], list) or not bindings["paths"]:
            raise SealError("connected path claim bindings are invalid")
        for path in bindings["paths"]:
            _validate_role_sequence(path, role_names)
    elif kind in {"certain_available", "certain_unavailable"}:
        if set(bindings) not in ({"case_role", "output_role"}, {"case_role", "output_role", "route_role"}):
            raise SealError("availability claim bindings are invalid")
        if not all(isinstance(bindings[key], str) and bindings[key] in role_names for key in bindings):
            raise SealError("availability claim uses an unresolved role")
    elif kind == "explicit_unknown":
        if set(bindings) != {"case_role", "basis_role"} or not all(isinstance(bindings[key], str) and bindings[key] in role_names for key in bindings):
            raise SealError("explicit-unknown claim bindings are invalid")
    elif kind == "dependency_path":
        if set(bindings) != {"changed_role", "affected_roles", "paths"} or not isinstance(bindings["changed_role"], str) or bindings["changed_role"] not in role_names:
            raise SealError("dependency claim bindings are invalid")
        affected = bindings["affected_roles"]
        if not isinstance(affected, list) or not affected or len(affected) != len(set(affected)) or not all(isinstance(role, str) and role in role_names for role in affected):
            raise SealError("dependency affected roles are invalid")
        if not isinstance(bindings["paths"], list) or not bindings["paths"]:
            raise SealError("dependency paths are invalid")
        for path in bindings["paths"]:
            _validate_role_sequence(path, role_names)


def seal(agent_visible: Path) -> dict[str, Any]:
    root = agent_visible.resolve()
    if root != Path(__file__).resolve().parent:
        raise SealError("helper may operate only on its own Agent-visible directory")
    contract, run_manifest = _read_object(root / "authoring-contract.json"), _read_object(root / "run-manifest.json")
    raw = _read_object(root / "semantic-package.json")
    expected_raw = {"principal", "invalid_candidate", "resource_roles", "edge_assertions", "closed_snapshot_absence_assertions", "cq_claims"}
    if contract.get("contract_version") != CONTRACT_VERSION or set(raw) != expected_raw:
        raise SealError("authoring content must contain the exact m7-contract-v4-recovery proof envelope")
    public_map = run_manifest.get("public_base_resource_map")
    if not isinstance(public_map, dict) or not public_map:
        raise SealError("run manifest lacks a public base map")
    candidates: dict[str, dict[str, Any]] = {}
    for name in ("principal", "invalid_candidate"):
        candidate = raw.get(name)
        if not isinstance(candidate, dict) or set(candidate) != {"items"} or not isinstance(candidate["items"], list) or not candidate["items"]:
            raise SealError(f"{name} must contain a non-empty items array")
        seen: set[str] = set()
        normalized = []
        for item in candidate["items"]:
            normalized_item = _normalize_item(item, public_map, seen)
            seen.add(normalized_item["client_item_id"])
            normalized.append(normalized_item)
        candidates[name] = {"items": normalized}
    proof = _validate_v3_proof(raw, candidates["principal"], public_map)
    package: dict[str, Any] = {
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "input_manifest_sha256": run_manifest.get("input_manifest_sha256"),
        "base_manifest_sha256": run_manifest.get("base_manifest_sha256"),
        "public_role_bindings": public_map,
        "principal": candidates["principal"],
        "invalid_candidate": candidates["invalid_candidate"],
        **proof,
    }
    if not all(isinstance(package[key], str) and package[key] for key in ("input_manifest_sha256", "base_manifest_sha256")):
        raise SealError("run manifest lacks input/base manifest hashes")
    package["principal_candidate_sha256"] = hashlib.sha256(canonical_json(package["principal"])).hexdigest()
    package["invalid_candidate_sha256"] = hashlib.sha256(canonical_json(package["invalid_candidate"])).hexdigest()
    package["seal"] = {"tool": SEAL_TOOL, "envelope_sha256": hashlib.sha256(canonical_json(package)).hexdigest()}
    temporary = root / ".semantic-package.json.tmp"
    temporary.write_bytes(canonical_json(package))
    temporary.replace(root / "semantic-package.json")
    return package


def runtime_check(agent_visible: Path) -> dict[str, Any]:
    """Write the sole L0 mutable receipt without reading a parent, a package or a platform."""
    root = agent_visible.resolve()
    if root != Path(__file__).resolve().parent:
        raise SealError("helper may operate only on its own Agent-visible directory")
    contract, manifest = _read_object(root / "l0-contract.json"), _read_object(root / "run-manifest.json")
    if (root / "semantic-package.json").exists():
        raise SealError("runtime-check staging must not contain a semantic package")
    expected_contract = {
        "contract_version": L0_RUNTIME_VERSION,
        "command": L0_COMMAND,
        "required_interpreter": "/usr/bin/python3",
        "nonce": "m7-l0-runtime-nonce-v1",
    }
    if contract != expected_contract:
        raise SealError("l0-contract.json drift")
    expected_manifest = {
        "contract_version",
        "run_id",
        "nonce",
        "command",
        "l0_contract_sha256",
        "helper_sha256",
        "staged_manifest_sha256",
    }
    if set(manifest) != expected_manifest or manifest.get("contract_version") != L0_RUNTIME_VERSION:
        raise SealError("L0 run manifest drift")
    helper_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    contract_hash = hashlib.sha256((root / "l0-contract.json").read_bytes()).hexdigest()
    if manifest.get("nonce") != contract["nonce"] or manifest.get("command") != L0_COMMAND or manifest.get("helper_sha256") != helper_hash:
        raise SealError("L0 helper identity or command drift")
    if manifest.get("l0_contract_sha256") != contract_hash or sys.executable != contract["required_interpreter"]:
        raise SealError("L0 contract or interpreter drift")
    receipt: dict[str, Any] = {
        "receipt_version": 1,
        "contract_version": L0_RUNTIME_VERSION,
        "run_id": manifest.get("run_id"),
        "nonce": manifest.get("nonce"),
        "command": L0_COMMAND,
        "run_manifest_sha256": hashlib.sha256(canonical_json(manifest)).hexdigest(),
        "helper_sha256": helper_hash,
        "interpreter": sys.executable,
        "python_version": platform.python_version(),
    }
    receipt["receipt_sha256"] = hashlib.sha256(canonical_json(receipt)).hexdigest()
    temporary = root / ".l0-runtime-receipt.json.tmp"
    temporary.write_bytes(canonical_json(receipt))
    temporary.replace(root / "l0-runtime-receipt.json")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Seal the one M7 Agent-visible semantic package.")
    parser.add_argument("--agent-visible", type=Path, required=True)
    parser.add_argument("--runtime-check", action="store_true")
    args = parser.parse_args()
    try:
        if args.runtime_check:
            runtime_check(args.agent_visible)
        else:
            seal(args.agent_visible)
    except SealError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
