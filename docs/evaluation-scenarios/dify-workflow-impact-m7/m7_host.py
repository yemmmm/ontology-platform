"""Fail-closed guarded Host phases for the frozen M7 contract.

``prepare`` creates one fresh scope and Agent-visible staging; ``continue`` resumes that exact scope
from its staged package; ``cleanup`` terminates a prepared run. Tests use a fake public-REST transport
and create no real Projects, Ontologies, or Modeling Batches.
"""

from __future__ import annotations

from copy import deepcopy
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any, Protocol
from urllib import error, request

from m7_contract import (
    AGENT_INPUT,
    BASE_SLICE,
    CONTRACT_VERSION,
    HOST_ONLY,
    SCENARIO_ROOT,
    SEALED_PACKAGE_KEYS,
    SEAL_TOOL,
    canonical_json,
    sealed_envelope_hash,
    validate_public_resource_map,
    verify_agent_input,
    verify_base_slice,
    verify_host_only,
)


ATTEMPT_LIMIT = 5
RUN_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,80}$")
ID_ONLY_FIELDS = {
    "create_property": ("class_id", "object_class_id"),
    "create_relation_type": ("source_class_id", "target_class_id"),
    "create_shape": ("target_class_id",),
}
IRI_FIELDS = {"create_relation": ("source_entity_iri", "relation_type_iri", "target_entity_iri")}
OUTPUT_CAPABLE_CREATE_KINDS = frozenset({"create_class", "create_relation_type", "create_shape", "create_entity"})
ABSOLUTE_IRI = re.compile(r"^https?://[^\s<>]+$")
SEMANTIC_KEY = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
ROLE_SOURCE_KEYS = {"public_role", "client_item_id"}
SNAPSHOT_ROW_CEILING = 9_999
JUDGE_STATUSES = frozenset({"PASS", "FAIL", "INCONCLUSIVE"})
JUDGE_REQUIRED_FILES = (
    "answer-contract-v1.json",
    "acceptance-contract.json",
)
ADDITIONAL_READ_QUERIES = {
    "rdf-snapshot": "SELECT ?s ?p ?o WHERE { ?s ?p ?o } ORDER BY STR(?s) STR(?p) STR(?o)",
    "triple-exists": "ASK WHERE { ?s ?p ?o }",
}


class HostError(RuntimeError):
    """A Host invariant failed; the caller must stop semantic writes."""


class BatchApi(Protocol):
    def read_session(self, scope: dict[str, str]) -> dict[str, Any]: ...

    def read_context(self, scope: dict[str, str]) -> dict[str, Any]: ...

    def acquire_lease(self, scope: dict[str, str]) -> str: ...

    def apply(self, request: dict[str, Any]) -> dict[str, Any]: ...


class AttemptLedger:
    """Scenario-global append-only ledger; cleanup never owns this file."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            # This read path intentionally does not apply the active contract version to prior
            # append-only events: v1/v2/v3 starts are historical evidence, not new v4 admission.
            return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line]
        except json.JSONDecodeError as error:
            raise HostError("attempt ledger is not valid JSONL") from error

    def append_modeling_started(self, event: dict[str, str]) -> None:
        required = {
            "event",
            "run_id",
            "agent_id",
            "fork_turns",
            "input_manifest_sha256",
            "base_manifest_sha256",
            "contract_version",
        }
        if set(event) != required or event.get("event") != "modeling_started":
            raise HostError("invalid modeling_started ledger event")
        if not RUN_ID.fullmatch(event["run_id"]) or event["fork_turns"] != "none":
            raise HostError("modeling start is not a fresh no-context run")
        if event["contract_version"] != CONTRACT_VERSION:
            raise HostError("modeling start contract version drift")
        prior = self.events()
        starts = [item for item in prior if item.get("event") == "modeling_started"]
        if len(starts) >= ATTEMPT_LIMIT:
            raise HostError("M7 modeling attempt limit reached")
        if len(starts) + 1 == ATTEMPT_LIMIT and not self._has_l1_pass_authorization(prior):
            raise HostError("attempt 5 requires an append-only L1 PASS authorization")
        if any(item.get("run_id") == event["run_id"] for item in starts):
            raise HostError("run_id already consumed by a modeling start")
        self._append(event)

    def append_l1_pass_authorized(self, event: dict[str, Any]) -> None:
        """Append the only authorization that can unlock a fifth L1 start; Producer never calls this."""
        required = {"event", "run_id", "scope", "judge_verdict_sha256", "contract_version"}
        if set(event) != required or event.get("event") != "l1_pass_authorized":
            raise HostError("invalid L1 PASS authorization ledger event")
        scope = event.get("scope")
        if not RUN_ID.fullmatch(str(event.get("run_id", ""))) or event.get("contract_version") != CONTRACT_VERSION or not isinstance(event.get("judge_verdict_sha256"), str) or not event["judge_verdict_sha256"]:
            raise HostError("L1 PASS authorization does not match the active v4 contract")
        if not isinstance(scope, dict) or set(scope) != {"project_id", "ontology_id", "build_session_id"} or not all(isinstance(value, str) and value for value in scope.values()):
            raise HostError("L1 PASS authorization scope is invalid")
        prior = self.events()
        starts = [item for item in prior if item.get("event") == "modeling_started"]
        if not any(item.get("run_id") == event["run_id"] and item.get("contract_version") == CONTRACT_VERSION for item in starts):
            raise HostError("L1 PASS authorization requires the paired active-v4 modeling start")
        if any(item.get("event") == "l1_pass_authorized" and item.get("run_id") == event["run_id"] for item in prior):
            raise HostError("L1 PASS authorization already exists for this run")
        self._append(event)

    def _has_l1_pass_authorization(self, events: list[dict[str, Any]]) -> bool:
        starts = {
            item.get("run_id")
            for item in events
            if item.get("event") == "modeling_started" and item.get("contract_version") == CONTRACT_VERSION
        }
        return any(
            isinstance(item, dict)
            and item.get("event") == "l1_pass_authorized"
            and item.get("contract_version") == CONTRACT_VERSION
            and item.get("run_id") in starts
            and isinstance(item.get("judge_verdict_sha256"), str)
            and item["judge_verdict_sha256"]
            for item in events
        )

    def _append(self, event: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("ab") as stream:
            stream.write(canonical_json(event) + b"\n")


def stage_run_manifest(
    scope: dict[str, str], public_map: object, input_manifest_sha256: str, base_manifest_sha256: str
) -> dict[str, Any]:
    required_scope = {"project_id", "ontology_id", "build_session_id"}
    if set(scope) != required_scope or not all(isinstance(value, str) and value for value in scope.values()):
        raise HostError("run scope must contain only fresh Project/Ontology/Build Session IDs")
    return {
        "contract_version": CONTRACT_VERSION,
        "scope": dict(scope),
        "public_base_resource_map": validate_public_resource_map(public_map),
        "input_manifest_sha256": input_manifest_sha256,
        "base_manifest_sha256": base_manifest_sha256,
        "permitted_locations": ["clarifications.jsonl", "semantic-package.json"],
    }


def candidate_hash(candidate: object) -> str:
    return hashlib.sha256(canonical_json(candidate)).hexdigest()


def validate_semantic_package(package: object, public_map: object, run_manifest: dict[str, Any]) -> str:
    if not isinstance(package, dict):
        raise HostError("semantic package must be an object")
    if set(package) != SEALED_PACKAGE_KEYS:
        raise HostError("semantic package is not the exact helper-sealed v3 envelope")
    resource_map = validate_public_resource_map(public_map)
    if package.get("schema_version") != 1 or package.get("contract_version") != CONTRACT_VERSION:
        raise HostError("semantic package schema or contract version drift")
    for field in ("input_manifest_sha256", "base_manifest_sha256"):
        if package.get(field) != run_manifest.get(field):
            raise HostError(f"semantic package {field} drift")
    if package.get("public_role_bindings") != resource_map:
        raise HostError("semantic package did not preserve the exact public base map")
    principal = package.get("principal")
    invalid = package.get("invalid_candidate")
    if not isinstance(principal, dict) or not isinstance(invalid, dict):
        raise HostError("semantic package lacks principal or invalid candidate")
    frozen, actual = package.get("principal_candidate_sha256"), candidate_hash(principal)
    if frozen != actual:
        raise HostError("principal candidate hash is not frozen")
    invalid_frozen, invalid_actual = package.get("invalid_candidate_sha256"), candidate_hash(invalid)
    if invalid_frozen != invalid_actual:
        raise HostError("invalid candidate hash is not frozen")
    seal = package.get("seal")
    if not isinstance(seal, dict) or set(seal) != {"tool", "envelope_sha256"}:
        raise HostError("semantic package lacks a helper sealing receipt")
    if seal.get("tool") != SEAL_TOOL or seal.get("envelope_sha256") != sealed_envelope_hash(package):
        raise HostError("semantic package sealing receipt drift")
    for name, candidate in (("principal", principal), ("invalid", invalid)):
        items = candidate.get("items")
        if not isinstance(items, list) or not items:
            raise HostError(f"{name} candidate lacks items")
        for item in items:
            _validate_item(item, resource_map)
    _validate_proof_grammar(package, resource_map, principal)
    return actual


def _validate_proof_grammar(package: dict[str, Any], public_map: dict[str, dict[str, str]], principal: dict[str, Any]) -> None:
    roles, assertions = package.get("resource_roles"), package.get("edge_assertions")
    absences, claims = package.get("closed_snapshot_absence_assertions"), package.get("cq_claims")
    if not all(isinstance(value, list) for value in (roles, assertions, absences, claims)):
        raise HostError("v3 proof fields must be arrays")
    commands = {item["client_item_id"]: item["command_kind"] for item in principal["items"]}
    role_sources: dict[str, dict[str, str]] = {}
    semantic_keys: set[str] = set()
    for entry in roles:
        if not isinstance(entry, dict) or set(entry) != {"role", "semantic_key", "source"}:
            raise HostError("resource_role has an invalid shape")
        role, semantic_key, source = entry.get("role"), entry.get("semantic_key"), entry.get("source")
        if not isinstance(role, str) or not RUN_ID.fullmatch(role) or role in role_sources or not isinstance(semantic_key, str) or not SEMANTIC_KEY.fullmatch(semantic_key) or semantic_key in semantic_keys or not isinstance(source, dict):
            raise HostError("resource_role is not unique")
        if set(source) == {"public_role"} and source["public_role"] in public_map:
            role_sources[role] = {"public_role": source["public_role"]}
        elif set(source) == {"client_item_id"} and commands.get(source["client_item_id"]) in OUTPUT_CAPABLE_CREATE_KINDS:
            role_sources[role] = {"client_item_id": source["client_item_id"]}
        else:
            raise HostError("resource_role must resolve to a public role or output-capable create item")
        semantic_keys.add(semantic_key)
    positive_ids: set[str] = set()
    absence_ids: set[str] = set()
    for entry, supplemental in [*( (item, False) for item in assertions), *((item, True) for item in absences)]:
        target_ids = absence_ids if supplemental else positive_ids
        assertion_id = _validate_assertion_shape(entry, role_sources, target_ids)
        target_ids.add(assertion_id)
    allowed_claim_kinds = {"connected_typed_path", "certain_available", "certain_unavailable", "explicit_unknown", "dependency_path"}
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != {"id", "kind", "assertion_ids", "bindings"} or not isinstance(claim.get("id"), str) or claim.get("kind") not in allowed_claim_kinds:
            raise HostError("cq_claim has an invalid shape")
        cited = claim.get("assertion_ids")
        if not isinstance(cited, list) or not cited or len(cited) != len(set(cited)) or not all(value in positive_ids for value in cited):
            raise HostError("cq_claim must cite only positive assertions")
        _validate_claim_bindings(claim["kind"], claim["bindings"], set(role_sources))


def _validate_assertion_shape(entry: object, roles: dict[str, dict[str, str]], known_ids: set[str]) -> str:
    if not isinstance(entry, dict) or set(entry) != {"id", "subject_role", "predicate", "object"}:
        raise HostError("edge assertion has an invalid shape")
    assertion_id, subject, predicate, operand = entry.get("id"), entry.get("subject_role"), entry.get("predicate"), entry.get("object")
    if not isinstance(assertion_id, str) or not RUN_ID.fullmatch(assertion_id) or assertion_id in known_ids:
        raise HostError("edge assertion ID is invalid or duplicated")
    if subject not in roles or not isinstance(predicate, dict) or not isinstance(operand, dict):
        raise HostError("edge assertion subject is unresolved")
    if set(predicate) == {"role"}:
        if predicate["role"] not in roles:
            raise HostError("edge assertion predicate role is unresolved")
    elif set(predicate) != {"iri"} or not isinstance(predicate.get("iri"), str) or not ABSOLUTE_IRI.fullmatch(predicate["iri"]):
        raise HostError("edge assertion predicate must be a role or absolute IRI")
    if set(operand) == {"role"}:
        if operand["role"] not in roles:
            raise HostError("edge assertion object role is unresolved")
    elif set(operand) == {"literal"}:
        literal = operand["literal"]
        if not isinstance(literal, dict) or set(literal) - {"value", "datatype", "language"} or not isinstance(literal.get("value"), str):
            raise HostError("edge assertion literal is invalid")
        if literal.get("datatype") is not None and (not isinstance(literal["datatype"], str) or not ABSOLUTE_IRI.fullmatch(literal["datatype"])):
            raise HostError("literal datatype must be an absolute IRI")
        if literal.get("language") is not None and (not isinstance(literal["language"], str) or not re.fullmatch(r"[A-Za-z]{1,8}(?:-[A-Za-z0-9]{1,8})*", literal["language"])):
            raise HostError("literal language is invalid")
        if literal.get("datatype") is not None and literal.get("language") is not None:
            raise HostError("literal cannot have datatype and language")
    else:
        raise HostError("edge assertion object must be a role or literal")
    return assertion_id


def _validate_claim_bindings(kind: str, bindings: object, role_names: set[str]) -> None:
    if not isinstance(bindings, dict):
        raise HostError("cq_claim bindings must be an object")
    def path(value: object) -> bool:
        return isinstance(value, list) and len(value) >= 2 and all(isinstance(role, str) and role in role_names for role in value)
    if kind == "connected_typed_path":
        if set(bindings) != {"paths"} or not isinstance(bindings["paths"], list) or not bindings["paths"] or not all(path(value) for value in bindings["paths"]):
            raise HostError("connected path claim bindings are invalid")
    elif kind in {"certain_available", "certain_unavailable"}:
        if set(bindings) not in ({"case_role", "output_role"}, {"case_role", "output_role", "route_role"}) or not all(isinstance(value, str) and value in role_names for value in bindings.values()):
            raise HostError("availability claim bindings are invalid")
    elif kind == "explicit_unknown":
        if set(bindings) != {"case_role", "basis_role"} or not all(isinstance(value, str) and value in role_names for value in bindings.values()):
            raise HostError("explicit-unknown claim bindings are invalid")
    elif kind == "dependency_path":
        affected, paths = bindings.get("affected_roles"), bindings.get("paths")
        if set(bindings) != {"changed_role", "affected_roles", "paths"} or bindings.get("changed_role") not in role_names or not isinstance(affected, list) or not affected or len(affected) != len(set(affected)) or not all(role in role_names for role in affected) or not isinstance(paths, list) or not paths or not all(path(value) for value in paths):
            raise HostError("dependency claim bindings are invalid")


def _validate_item(item: object, resource_map: dict[str, dict[str, str]]) -> None:
    expected_fields = {
        "client_item_id",
        "command_kind",
        "payload",
        "depends_on",
        "evidence_reference_ids",
        "evidence",
        "rationale",
        "competency_question_ids",
    }
    if not isinstance(item, dict) or set(item) != expected_fields or not isinstance(item.get("command_kind"), str):
        raise HostError("semantic item lacks command_kind")
    if not isinstance(item.get("client_item_id"), str) or not item["client_item_id"]:
        raise HostError("semantic item lacks client_item_id")
    if not all(isinstance(item.get(field), list) for field in ("depends_on", "evidence_reference_ids", "evidence", "competency_question_ids")):
        raise HostError("semantic item has invalid workflow metadata")
    if item["evidence_reference_ids"] or item["competency_question_ids"]:
        raise HostError("v4 semantic items require empty Evidence and CompetencyQuestion ID arrays")
    if item["rationale"] is not None and not isinstance(item["rationale"], str):
        raise HostError("semantic item rationale is invalid")
    payload = item.get("payload")
    if not isinstance(payload, dict):
        raise HostError("semantic item payload is invalid")
    command = item["command_kind"]
    if command not in published_command_kinds():
        raise HostError(f"unpublished command_kind: {command}")
    for field in ID_ONLY_FIELDS.get(command, ()):
        _validate_base_reference(payload.get(field), resource_map, "resource_id", field)
    if command == "create_shape":
        constraints = payload.get("constraints", [])
        if not isinstance(constraints, list):
            raise HostError("Shape constraints must be a list")
        for constraint in constraints:
            if isinstance(constraint, dict) and "path_id" in constraint:
                _validate_base_reference(constraint["path_id"], resource_map, "resource_id", "path_id")
    for field in IRI_FIELDS.get(command, ()):
        _validate_base_reference(payload.get(field), resource_map, "resource_iri", field)


def _validate_base_reference(value: object, resource_map: dict[str, dict[str, str]], key: str, field: str) -> None:
    if isinstance(value, dict) and set(value) == {"item_ref"}:
        reference = value["item_ref"]
        if not isinstance(reference, dict) or reference.get("output") != key:
            raise HostError(f"{field} requires {key}, not the swapped representation")
        return
    allowed = {resource[key] for resource in resource_map.values()}
    opposite_key = "resource_iri" if key == "resource_id" else "resource_id"
    opposite = {resource[opposite_key] for resource in resource_map.values()}
    if value in opposite:
        raise HostError(f"{field} requires {key}, not the swapped representation")
    if not isinstance(value, str) or value not in allowed:
        raise HostError(f"{field} is not an exact public {key}")


def apply_with_fresh_lease(
    api: BatchApi, scope: dict[str, str], candidate: dict[str, Any], expected_workspace_version: int
) -> dict[str, Any]:
    """Apply one frozen candidate, with only the exact pre-attempt expiry recovery."""
    frozen_hash = candidate_hash(candidate)
    request_without_lease: dict[str, Any] | None = None
    for number in range(2):
        session, context = api.read_session(scope), api.read_context(scope)
        _verify_pre_apply(scope, session, context, expected_workspace_version, candidate, frozen_hash)
        lease_token = api.acquire_lease(scope)
        request = {
            "scope": dict(scope),
            "mode": "apply_atomic",
            "expected_workspace_version": expected_workspace_version,
            "candidate": candidate,
            "candidate_sha256": frozen_hash,
            "client_batch_id": f"m7-{frozen_hash[:20]}",
            "idempotency_key": f"m7-apply-{frozen_hash}",
            "lease_token": lease_token,
        }
        stable = {key: value for key, value in request.items() if key != "lease_token"}
        if request_without_lease is None:
            request_without_lease = stable
        elif stable != request_without_lease:
            raise HostError("retry request drifted beyond lease token")
        result = api.apply(request)
        if result.get("status") == "applied":
            return result
        precise_expiry = (
            result.get("error_code") == "lease_expired"
            and result.get("attempt_persisted") is False
            and result.get("committed") is False
        )
        if number == 0 and precise_expiry:
            continue
        raise HostError("apply failed closed; no semantic resubmission is permitted")
    raise HostError("second lease expiry must fail closed")


def _verify_pre_apply(
    scope: dict[str, str],
    session: dict[str, Any],
    context: dict[str, Any],
    expected: int,
    candidate: object,
    frozen: str,
) -> None:
    if session.get("status") != "active" or any(session.get(key) != value for key, value in scope.items()):
        raise HostError("Build Session scope is no longer active and exact")
    if context.get("workspace_version") != expected:
        raise HostError("workspace version drift before apply")
    if candidate_hash(candidate) != frozen:
        raise HostError("candidate changed before apply")


def require_complete_query(request: dict[str, Any], response: dict[str, Any], needs_two_streams: bool) -> None:
    if request.get("match_cursor") and request.get("context_cursor"):
        raise HostError("Semantic Context Query cannot send two cursor kinds")
    if needs_two_streams and request.get("kind") != "bounded_ontology_sparql":
        raise HostError("two-stream CQ proof requires bounded ontology-scoped SPARQL")
    if response.get("scope_complete") is not True or response.get("truncated") is True:
        raise HostError("CQ result is incomplete or truncated")
    if response.get("completeness") == "degraded" or not response.get("proof_resources"):
        raise HostError("CQ result is degraded or lacks public proof resources")


def mutate_projection(projection: dict[str, Any], mutation: str) -> dict[str, Any]:
    """Return an isolated deterministic mutation without an Agent or platform write."""
    result = deepcopy(projection)
    if mutation == "remove_score_binding":
        result["bindings"] = [item for item in result["bindings"] if item.get("id") != "c-to-b-score"]
    elif mutation == "incompatible_quality_type":
        result["variables"]["quality_rating"]["datatype"] = "xsd:boolean"
    elif mutation == "unavailable_branch_output":
        result["output_uses"].append({"branch": "failing", "variable": "approved_content"})
    elif mutation == "same_name_decoy":
        result["nodes"].append({"id": "decoy-template", "name": "Template", "bound": False})
    else:
        raise HostError("unknown deterministic mutation")
    return result


def published_command_kinds() -> frozenset[str]:
    """Load the frozen public command inventory and compare it to the real handler registry."""
    frozen = json.loads((HOST_ONLY / "published-command-kinds.json").read_text(encoding="utf-8"))
    if frozen.get("contract_version") != CONTRACT_VERSION:
        raise HostError("published command contract version drift")
    values = frozen.get("command_kinds")
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        raise HostError("published command inventory is invalid")
    try:
        from app.core.config import Settings
        from app.services.modeling_handlers import ModelingCommandHandlerRegistry
    except ImportError as error:
        raise HostError("real Modeling Batch compiler is unavailable for preflight") from error
    actual = set(ModelingCommandHandlerRegistry(Settings()).command_kinds)
    if set(values) != actual:
        raise HostError("frozen command inventory drifted from the real Modeling Batch compiler")
    return frozenset(values)


def compiler_preflight(items: list[dict[str, Any]], ontology_id: str = "m7-preflight") -> None:
    """Resolve same-Batch refs and execute only real compiler preparation; it never writes."""
    try:
        from app.core.config import Settings
        from app.services.modeling_handlers import ModelingCommandHandlerRegistry
    except ImportError as error:
        raise HostError("real Modeling Batch compiler is unavailable for preflight") from error
    registry = ModelingCommandHandlerRegistry(Settings())
    outputs: dict[str, dict[str, str]] = {}

    def resolve(value: Any) -> Any:
        if isinstance(value, dict):
            if set(value) == {"item_ref"}:
                ref = value["item_ref"]
                if not isinstance(ref, dict):
                    raise HostError("item_ref must be an object")
                item_id, output = ref.get("client_item_id"), ref.get("output")
                if not isinstance(item_id, str) or output not in {"resource_id", "resource_iri"}:
                    raise HostError("item_ref is invalid")
                if item_id not in outputs or output not in outputs[item_id]:
                    raise HostError("item_ref cannot be resolved in deterministic order")
                return outputs[item_id][output]
            return {key: resolve(child) for key, child in value.items()}
        if isinstance(value, list):
            return [resolve(child) for child in value]
        return value

    for ordinal, item in enumerate(items):
        if not isinstance(item, dict):
            raise HostError("compiler preflight item is not an object")
        command, client_item_id, payload = item.get("command_kind"), item.get("client_item_id"), item.get("payload")
        if command not in published_command_kinds() or not isinstance(client_item_id, str) or not isinstance(payload, dict):
            raise HostError("compiler preflight item is unsupported")
        prepared = registry.prepare(
            batch_id="m7-offline-preflight",
            ontology_id=ontology_id,
            client_item_id=client_item_id,
            command_kind=command,
            payload=resolve(payload),
        )
        outputs[client_item_id] = prepared.outputs


class RestTransport(Protocol):
    """Small public-REST boundary used by the guarded Host and no-write tests."""

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]: ...


class UrllibRestTransport:
    """Authenticated public REST transport; all semantic decisions remain outside the transport."""

    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if body is None else canonical_json(body)
        call = request.Request(
            f"{self.base_url}{path}", data=data, method=method,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        try:
            with request.urlopen(call, timeout=30) as response:  # noqa: S310 - explicit configured endpoint
                raw = response.read()
                return {"status": response.status, "body": json.loads(raw) if raw else {}}
        except error.HTTPError as response:
            raw = response.read()
            return {"status": response.code, "body": json.loads(raw) if raw else {}}


def prepare_guarded(
    transport: RestTransport, *, run_id: str, runtime_root: Path, execute_guarded: bool = False
) -> dict[str, Any]:
    """Create and stage one fresh base scope; never requires an Agent semantic package."""
    _require_guard(run_id, execute_guarded)
    root = _new_runtime_root(runtime_root, run_id)
    project_id: str | None = None
    state_path = root / "host-only-state.json"
    evidence: dict[str, Any] = {"phase": "prepare", "run_id": run_id}
    try:
        input_manifest, base_manifest = verify_agent_input(), verify_base_slice()
        host_manifest = verify_host_only()
        base_package = json.loads((BASE_SLICE / "semantic-package.json").read_text(encoding="utf-8"))
        compiler_preflight(base_package["items"])
        project = _ok(transport.request("POST", "/api/projects", {"name": f"M7 {run_id}", "description": "M7 owned scope"}))
        project_id = _required_str(project, "id")
        ontology = _ok(transport.request("POST", f"/api/projects/{project_id}/ontologies", {"name": f"M7 {run_id}", "description": "M7 owned ontology", "external_mappings": {}}))
        ontology_id = _required_str(ontology, "id")
        created = _ok(transport.request("POST", f"/api/projects/{project_id}/build-sessions", {"client_session_id": f"{run_id}-session"}))
        session_id = _required_str(created, "id")
        scope = {"project_id": project_id, "ontology_id": ontology_id, "build_session_id": session_id}
        base_dry = _submit_dry_run(transport, scope, base_package["items"], "base")
        base_apply = _apply_frozen_dry_run(transport, scope, base_package["items"], "base", base_dry)
        public_map = _public_map_from_results(base_apply, base_package["public_role_client_item_ids"])
        base_probe = _probe_public_routes(transport, scope)
        run_manifest = stage_run_manifest(scope, public_map, _manifest_digest(input_manifest), _manifest_digest(base_manifest))
        staged = _stage_agent_visible(root, run_manifest)
        state = {
            "state_version": 1,
            "status": "PREPARED",
            "run_id": run_id,
            "scope": scope,
            "workspace": {"base_frozen_version": base_dry["_frozen_workspace_version"], **base_probe["scope"]},
            "base_dry_run": base_dry,
            "base_apply": base_apply,
            "public_base_resource_map": public_map,
            "contract_hashes": {"input": _manifest_digest(input_manifest), "base": _manifest_digest(base_manifest), "host": _manifest_digest(host_manifest)},
            "run_manifest_sha256": staged["run_manifest_sha256"],
            "staged_manifest_sha256": staged["staged_manifest_sha256"],
            "agent_visible_dir": str(root / "agent-visible"),
            "cleanup": None,
        }
        _write_json(state_path, state)
        evidence.update({"scope": scope, "base_dry_run": base_dry, "base_apply": base_apply, "base_probe": base_probe, "staged": staged, "status": "PREPARED"})
        _write_json(root / "prepare-evidence.json", evidence)
        return {"state_path": str(state_path), "agent_visible_dir": state["agent_visible_dir"], "run_manifest": run_manifest}
    except Exception as exc:
        cleanup = _cleanup_owned(transport, project_id)
        evidence.update({"status": "FAILED", "error": str(exc), "cleanup": cleanup})
        _write_json(root / "prepare-evidence.json", evidence)
        raise


def continue_guarded(
    transport: RestTransport,
    *,
    state_path: Path,
    execute_guarded: bool = False,
) -> dict[str, Any]:
    """Complete Producer work and stop with a sealed public bundle for a fresh Judge."""
    if execute_guarded is not True:
        raise HostError("refusing runtime mutation without --execute-guarded")
    state = _load_prepared_state(state_path)
    root = state_path.parent
    evidence: dict[str, Any] = {"phase": "continue", "run_id": state["run_id"], "scope": state["scope"]}
    primary_error: Exception | None = None
    try:
        _verify_staged_state(state)
        scope = state["scope"]
        agent_visible = root / "agent-visible"
        run_manifest = json.loads((agent_visible / "run-manifest.json").read_text(encoding="utf-8"))
        try:
            semantic_package = json.loads((agent_visible / "semantic-package.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HostError("Agent-visible semantic package is missing or invalid") from exc
        if not isinstance(semantic_package, dict):
            raise HostError("Agent-visible semantic package is not an object")
        validate_semantic_package(semantic_package, state["public_base_resource_map"], run_manifest)
        compiler_preflight(semantic_package["principal"]["items"], scope["ontology_id"])
        principal_dry = _submit_dry_run(transport, scope, semantic_package["principal"]["items"], "principal")
        role_map = _role_map_from_dry_run(semantic_package, state["public_base_resource_map"], principal_dry)
        assertion_queries = compile_frozen_assertion_queries(
            semantic_package, role_map, principal_dry.get("normalized_delta")
        )
        frozen_query_hashes = {name: candidate_hash(query) for name, query in assertion_queries.items()}
        invalid_dry = _submit_dry_run(
            transport,
            scope,
            semantic_package["invalid_candidate"]["items"],
            "invalid",
            require_validated=False,
        )
        _require_invalid_rejected(invalid_dry)
        principal_apply = _apply_frozen_dry_run(transport, scope, semantic_package["principal"]["items"], "principal", principal_dry)
        _apply_outputs_equal(principal_dry, principal_apply)
        verification = _probe_public_routes(transport, scope)
        _require_scope_matches(verification["scope"], state["workspace"], scope["ontology_id"])
        cq_results = _execute_frozen_assertions(
            transport, scope, assertion_queries, semantic_package, verification["scope"], role_map
        )
        session = _session_envelope(transport, scope["build_session_id"])
        revision = _active_revision(session)
        checkpoint = _ok(transport.request("POST", f"/api/build-sessions/{scope['build_session_id']}/checkpoints", {"client_checkpoint_id": f"{state['run_id']}-checkpoint", "expected_revision": revision, "phase": "verification", "current_step": "M7 CQ proof complete", "next_step": "complete", "ontology_id": scope["ontology_id"], "summary": "Base, principal, invalid candidate, validation, reasoning and CQs recorded."}))
        completed = _ok(transport.request("POST", f"/api/build-sessions/{scope['build_session_id']}:complete", {"client_request_id": f"{state['run_id']}-complete", "expected_revision": revision + 1, "summary": "M7 guarded Host execution completed.", "unresolved_items": []}))
        producer = {
            "principal_dry_run": principal_dry,
            "principal_apply": principal_apply,
            "invalid_dry_run": invalid_dry,
            "role_map": role_map,
            "frozen_query_hashes": frozen_query_hashes,
            "verification": verification,
            "producer_claim_query_evidence": cq_results,
            "checkpoint": checkpoint,
            "completed": completed,
        }
        bundle = _seal_public_evidence_bundle(
            transport, root=root, state=state, semantic_package=semantic_package, producer=producer
        )
        boundary = _seal_producer_evidence_boundary(state, bundle)
        state.update({
            "status": "PRODUCER_EVIDENCE_SEALED",
            "public_evidence": bundle,
            "producer_evidence_boundary": boundary,
            "cleanup": None,
        })
        _write_json(state_path, state)
        judge = _stage_judge(root, state, bundle)
        evidence.update({"status": "AWAITING_JUDGE", **producer, "public_evidence": bundle, "judge": judge})
        state.update({"status": "AWAITING_JUDGE", "public_evidence": bundle, "judge": judge, "cleanup": None})
        _write_json(state_path, state)
        _write_json(root / "host-evidence.json", evidence)
        return evidence
    except Exception as exc:
        primary_error = exc
        evidence.update({"status": "FAILED", "error": str(exc)})
    cleanup = _cleanup_owned(transport, state["scope"]["project_id"])
    evidence["cleanup"] = cleanup
    terminal_status = "FAILED" if cleanup["success"] is True else "CLEANUP_FAILED"
    state.update({"status": terminal_status, "cleanup": cleanup, "primary_cause": str(primary_error)})
    evidence["status"] = terminal_status
    _write_json(state_path, state)
    _write_json(root / "host-evidence.json", evidence)
    raise primary_error


def cleanup_guarded(transport: RestTransport, *, state_path: Path, execute_guarded: bool = False) -> dict[str, Any]:
    """Terminate an active retained scope without creating a replacement scope."""
    if execute_guarded is not True:
        raise HostError("refusing runtime mutation without --execute-guarded")
    state = _load_state(state_path)
    if state.get("status") in {"CLEANED", "FAILED", "CLEANUP_FAILED"}:
        return _load_exact_object(state_path.parent / "terminal-receipt.json", "cleanup receipt")
    if state.get("status") not in {"PREPARED", "AWAITING_JUDGE", "AWAITING_L2_CONSUMER"}:
        raise HostError("cleanup requires an active M7 state")
    cleanup = _cleanup_owned(transport, state["scope"]["project_id"])
    terminal_status = "CLEANED" if cleanup["success"] is True else "CLEANUP_FAILED"
    state.update({"status": terminal_status, "cleanup": cleanup})
    _write_json(state_path, state)
    receipt = {"run_id": state["run_id"], "status": terminal_status, "primary_cause": "manual_cleanup", "cleanup": cleanup}
    _write_json(state_path.parent / "cleanup-evidence.json", {"phase": "cleanup", **receipt, "scope": state["scope"]})
    _write_json(state_path.parent / "terminal-receipt.json", receipt)
    if cleanup["success"] is not True:
        raise HostError("owned cleanup failed")
    return cleanup


def _require_guard(run_id: str, execute_guarded: bool) -> None:
    if execute_guarded is not True:
        raise HostError("refusing runtime mutation without --execute-guarded")
    if not RUN_ID.fullmatch(run_id):
        raise HostError("unsafe run_id")


def _new_runtime_root(runtime_root: Path, run_id: str) -> Path:
    root = runtime_root / run_id
    if root.exists():
        raise HostError("run root already exists; a prepared/failed scope cannot be reused")
    root.mkdir(parents=True)
    return root


def _stage_agent_visible(root: Path, run_manifest: dict[str, Any]) -> dict[str, str]:
    visible = root / "agent-visible"
    shutil.copytree(AGENT_INPUT, visible)
    _write_json(visible / "run-manifest.json", run_manifest)
    (visible / "clarifications.jsonl").touch()
    (visible / "semantic-package.json").touch()
    staged_manifest = _write_directory_manifest(visible, "staged-manifest.json")
    return {"run_manifest_sha256": _sha256_file(visible / "run-manifest.json"), "staged_manifest_sha256": _manifest_digest(staged_manifest)}


def _write_directory_manifest(
    root: Path, name: str, *, mutable_files: set[str] | None = None
) -> dict[str, Any]:
    mutable_files = mutable_files or {"clarifications.jsonl", "semantic-package.json"}
    files = [
        {"path": path.relative_to(root).as_posix(), "sha256": _sha256_file(path)}
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != name and path.relative_to(root).as_posix() not in mutable_files
    ]
    manifest = {"manifest_version": 1, "files": files, "mutable_files": sorted(mutable_files)}
    _write_json(root / name, manifest)
    return manifest


def _verify_staged_state(state: dict[str, Any]) -> None:
    root = Path(state["agent_visible_dir"])
    if root.name != "agent-visible" or (root / "host-only-state.json").exists():
        raise HostError("Agent-visible root is invalid")
    if not (root.parent / "host-only-state.json").is_file():
        raise HostError("host-only state is outside the staged run root")
    manifest_path = root / "staged-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if _manifest_digest(manifest) != state.get("staged_manifest_sha256"):
        raise HostError("staged manifest hash drift")
    mutable = manifest.get("mutable_files")
    if mutable != ["clarifications.jsonl", "semantic-package.json"]:
        raise HostError("staged mutable output declaration drift")
    declared = {entry.get("path") for entry in manifest.get("files", []) if isinstance(entry, dict)}
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path != manifest_path and path.relative_to(root).as_posix() not in mutable
    }
    if declared != actual:
        raise HostError("staged Agent-visible membership drift")
    for entry in manifest["files"]:
        path = root / entry["path"]
        if _sha256_file(path) != entry.get("sha256"):
            raise HostError(f"staged Agent-visible hash drift: {entry['path']}")
    run_manifest = root / "run-manifest.json"
    if _sha256_file(run_manifest) != state.get("run_manifest_sha256"):
        raise HostError("run manifest hash drift")
    if json.loads(run_manifest.read_text(encoding="utf-8")).get("scope") != state.get("scope"):
        raise HostError("run manifest scope drift")


def _load_state(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HostError("host-only state is missing or invalid") from exc
    if not isinstance(value, dict) or not isinstance(value.get("scope"), dict):
        raise HostError("host-only state has no scope")
    return value


def _load_prepared_state(path: Path) -> dict[str, Any]:
    state = _load_state(path)
    if state.get("status") != "PREPARED":
        raise HostError("continue requires a PREPARED state")
    return state


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(canonical_json(value))
    temporary.replace(path)


def _manifest_digest(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(manifest)).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ok(response: dict[str, Any]) -> dict[str, Any]:
    if response.get("status") not in {200, 201, 204}:
        detail = response.get("body", {}).get("detail", {}) if isinstance(response.get("body"), dict) else {}
        code = detail.get("code") if isinstance(detail, dict) else None
        raise HostError(f"REST request failed closed: {code or response.get('status')}")
    body = response.get("body", {})
    if not isinstance(body, dict):
        raise HostError("REST response body is not an object")
    return body


def _required_str(value: dict[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise HostError(f"REST response lacks {key}")
    return result


def _session_envelope(transport: RestTransport, session_id: str) -> dict[str, Any]:
    body = _ok(transport.request("GET", f"/api/build-sessions/{session_id}"))
    session = body.get("session")
    if not isinstance(session, dict):
        raise HostError("Build Session GET response lacks body.session")
    return session


def _active_revision(session: dict[str, Any]) -> int:
    revision = session.get("revision")
    if session.get("status") != "active" or not isinstance(revision, int):
        raise HostError("Build Session is not active before apply")
    return revision


def _workspace_version(transport: RestTransport, ontology_id: str) -> str:
    context = _ok(transport.request("GET", f"/api/ontologies/{ontology_id}/modeling-context"))
    workspace = context.get("workspace")
    version = workspace.get("workspace_version") if isinstance(workspace, dict) else None
    if not isinstance(version, str) or not version:
        raise HostError("modeling context lacks a ready workspace version")
    return version


def _submit_dry_run(
    transport: RestTransport,
    scope: dict[str, str],
    items: list[dict[str, Any]],
    name: str,
    *,
    require_validated: bool = True,
) -> dict[str, Any]:
    version = _workspace_version(transport, scope["ontology_id"])
    items_hash = candidate_hash(items)
    body = {"client_batch_id": f"{name}-{items_hash[:20]}", "ontology_id": scope["ontology_id"], "idempotency_key": f"m7-{name}-{items_hash}-dry", "expected_workspace_version": version, "mode": "dry_run", "items": items}
    result = _ok(transport.request("POST", f"/api/build-sessions/{scope['build_session_id']}/modeling-batches", body))
    expected_status = "validated" if require_validated else "validation_failed"
    if result.get("attempt_status") != expected_status:
        raise HostError(
            f"{name} dry-run expected {expected_status}; {_dry_run_diagnostics(result)}"
        )
    workspace = result.get("workspace")
    if not isinstance(workspace, dict):
        raise HostError(f"{name} dry-run lacks workspace receipt")
    expected, before = workspace.get("expected_version"), workspace.get("before_version")
    if expected != version or before != version:
        raise HostError(f"{name} dry-run workspace receipt drift")
    return {**result, "_frozen_items_sha256": items_hash, "_frozen_workspace_version": version}


def _dry_run_diagnostics(result: dict[str, Any]) -> str:
    """Keep enough failed dry-run evidence for offline diagnosis without embedding a full response."""
    findings = result.get("findings")
    blocking: list[str] = []
    if isinstance(findings, list):
        for finding in findings:
            if not isinstance(finding, dict) or finding.get("blocking") is not True:
                continue
            code, message = finding.get("code"), finding.get("message")
            if isinstance(code, str) or isinstance(message, str):
                blocking.append(f"{code or 'unknown'}:{message or ''}"[:300])
            if len(blocking) == 3:
                break
    return f"attempt_status={result.get('attempt_status')!r}; blocking_findings={blocking}"


def _apply_frozen_dry_run(transport: RestTransport, scope: dict[str, str], items: list[dict[str, Any]], name: str, dry: dict[str, Any]) -> dict[str, Any]:
    items_hash, frozen = dry.get("_frozen_items_sha256"), dry.get("_frozen_workspace_version")
    if items_hash != candidate_hash(items) or not isinstance(frozen, str):
        raise HostError("apply candidate differs from frozen dry-run")
    client_batch_id = dry.get("client_batch_id")
    if not isinstance(client_batch_id, str):
        raise HostError("dry-run lacks client_batch_id")
    for retry in range(2):
        revision = _active_revision(_session_envelope(transport, scope["build_session_id"]))
        if _workspace_version(transport, scope["ontology_id"]) != frozen:
            raise HostError("workspace version drift after dry-run")
        lease = _ok(transport.request("POST", f"/api/build-sessions/{scope['build_session_id']}/ontology-leases/{scope['ontology_id']}:acquire", {"client_request_id": f"{name}-lease-{retry}", "expected_session_revision": revision, "rotate_token": True}))
        token = _required_str(lease, "lease_token")
        response = transport.request("POST", f"/api/build-sessions/{scope['build_session_id']}/modeling-batches", {"client_batch_id": client_batch_id, "ontology_id": scope["ontology_id"], "idempotency_key": f"m7-{name}-{items_hash}-apply", "expected_workspace_version": frozen, "mode": "apply_atomic", "lease_token": token, "items": items})
        if response.get("status") in {200, 201}:
            return _ok(response)
        detail = response.get("body", {}).get("detail", {}) if isinstance(response.get("body"), dict) else {}
        precise = isinstance(detail, dict) and detail.get("code") == "lease_expired" and detail.get("attempt_persisted") is False and detail.get("committed") is False
        if retry == 0 and precise:
            continue
        raise HostError("apply failed closed; no duplicate semantic submission is permitted")
    raise HostError("second lease expiry must fail closed")


def _public_map_from_results(response: dict[str, Any], roles: dict[str, str]) -> dict[str, dict[str, str]]:
    outputs = {item.get("client_item_id"): item.get("resource_outputs") for item in response.get("items", []) if isinstance(item, dict)}
    result: dict[str, dict[str, str]] = {}
    for role, item_id in roles.items():
        item_outputs = outputs.get(item_id)
        if not isinstance(item_outputs, dict):
            raise HostError(f"base apply lacks outputs for public role {role}")
        result[role] = {"resource_id": _required_str(item_outputs, "resource_id"), "resource_iri": _required_str(item_outputs, "resource_iri")}
    return validate_public_resource_map(result)


def _role_map_from_dry_run(package: dict[str, Any], public_map: object, dry_run: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Resolve only sealed roles from exact dry-run outputs; relations deliberately have no role."""
    base = validate_public_resource_map(public_map)
    outputs = {
        item.get("client_item_id"): item.get("resource_outputs")
        for item in dry_run.get("items", [])
        if isinstance(item, dict)
    }
    principal_kinds = {
        item["client_item_id"]: item["command_kind"] for item in package["principal"]["items"]
    }
    result: dict[str, dict[str, str]] = {}
    for binding in package["resource_roles"]:
        role, source = binding["role"], binding["source"]
        if "public_role" in source:
            result[role] = {**base[source["public_role"]], "semantic_key": binding["semantic_key"]}
            continue
        item_id = source["client_item_id"]
        if principal_kinds.get(item_id) not in OUTPUT_CAPABLE_CREATE_KINDS:
            raise HostError("create_relation cannot be a resource role")
        output = outputs.get(item_id)
        if not isinstance(output, dict):
            raise HostError(f"dry-run lacks resource outputs for role {role}")
        result[role] = {"resource_id": _required_str(output, "resource_id"), "resource_iri": _required_str(output, "resource_iri"), "semantic_key": binding["semantic_key"]}
    validate_public_resource_map({role: {key: value[key] for key in ("resource_id", "resource_iri")} for role, value in result.items()})
    iris = [value["resource_iri"] for value in result.values()]
    if len(iris) != len(set(iris)):
        raise HostError("resource roles resolve to duplicate IRIs")
    return result


def _delta_predicates(normalized_delta: object) -> set[str]:
    """Extract absolute predicate IRIs conservatively from the public normalized-delta JSON."""
    found: set[str] = set()
    def walk(value: object, predicate_context: bool = False) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                is_predicate = predicate_context or key.lower() in {"predicate", "p", "predicate_iri"}
                if is_predicate and isinstance(child, str) and ABSOLUTE_IRI.fullmatch(child):
                    found.add(child)
                walk(child, is_predicate)
        elif isinstance(value, list):
            for child in value:
                walk(child, predicate_context)
        elif predicate_context and isinstance(value, str) and ABSOLUTE_IRI.fullmatch(value):
            found.add(value)
    walk(normalized_delta)
    return found


def _literal_sparql(value: dict[str, Any]) -> str:
    escaped = value["value"].replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    if value.get("datatype"):
        return f'"{escaped}"^^<{value["datatype"]}>'
    if value.get("language"):
        return f'"{escaped}"@{value["language"]}'
    return f'"{escaped}"'


def compile_frozen_assertion_queries(package: dict[str, Any], role_map: dict[str, dict[str, str]], normalized_delta: object) -> dict[str, str]:
    """Compile sealed proof grammar into bounded public-SPARQL; no caller query text enters here."""
    delta_predicates = _delta_predicates(normalized_delta)
    compiled: dict[str, str] = {}
    for entry in [*package["edge_assertions"], *package["closed_snapshot_absence_assertions"]]:
        subject = f'<{role_map[entry["subject_role"]]["resource_iri"]}>'
        predicate = entry["predicate"]
        if "role" in predicate:
            predicate_text = f'<{role_map[predicate["role"]]["resource_iri"]}>'
        else:
            iri = predicate["iri"]
            if iri not in delta_predicates:
                raise HostError("absolute predicate is absent from the principal normalized delta")
            predicate_text = f"<{iri}>"
        operand = entry["object"]
        object_text = f'<{role_map[operand["role"]]["resource_iri"]}>' if "role" in operand else _literal_sparql(operand["literal"])
        compiled[entry["id"]] = f"ASK WHERE {{ {subject} {predicate_text} {object_text} }}"
    return compiled


def _apply_outputs_equal(dry_run: dict[str, Any], apply: dict[str, Any]) -> None:
    def selected(value: dict[str, Any]) -> dict[str, object]:
        return {
            item.get("client_item_id"): item.get("resource_outputs")
            for item in value.get("items", [])
            if isinstance(item, dict)
        }
    if selected(dry_run) != selected(apply):
        raise HostError("apply resource outputs drifted from the validated dry-run")


def _require_invalid_rejected(response: dict[str, Any]) -> None:
    findings = response.get("findings")
    if response.get("attempt_status") != "validation_failed" or not isinstance(findings, list):
        raise HostError("invalid candidate dry-run did not reject with findings")
    if not any(isinstance(finding, dict) and finding.get("blocking") is True for finding in findings):
        raise HostError("invalid candidate lacks a blocking semantic finding")


def _terminal(value: dict[str, Any], label: str) -> None:
    status = value.get("status")
    if not isinstance(status, str) or status.lower() in {"failed", "error", "running", "pending"}:
        raise HostError(f"{label} did not reach a successful terminal status")


def _scope_from_response(response: dict[str, Any], ontology_id: str) -> dict[str, Any]:
    scope = response.get("scope")
    if not isinstance(scope, dict) or scope.get("status") != "complete" or scope.get("excluded_ontologies"):
        raise HostError("scoped query is incomplete or has excluded Ontologies")
    ontologies = scope.get("ontologies")
    if not isinstance(ontologies, list) or len(ontologies) != 1 or not isinstance(ontologies[0], dict):
        raise HostError("scoped query must resolve exactly one Ontology")
    item = ontologies[0]
    if item.get("ontology_id") != ontology_id:
        raise HostError("scoped query resolved a different Ontology")
    warnings = response.get("warnings")
    if response.get("truncated") is True or not isinstance(warnings, list) or any(
        isinstance(warning, dict) and any(token in str(warning.get("code", "")).lower() for token in ("stale", "supersed", "truncat"))
        for warning in warnings
    ):
        raise HostError("scoped query is truncated or stale")
    for key in ("workspace_version", "source_signature"):
        if not isinstance(item.get(key), str) or not item[key]:
            raise HostError(f"scoped query lacks {key}")
    return {"workspace_version": item["workspace_version"], "source_signature": item["source_signature"], "graph_set_id": item.get("derived_state", {}).get("graph_set_id")}


def _require_scope_matches(actual: dict[str, Any], expected: dict[str, Any], ontology_id: str) -> None:
    expected_graph_set = expected.get("graph_set_id")
    if expected_graph_set is not None:
        actual_graph_set = actual.get("graph_set_id")
        if not isinstance(expected_graph_set, str) or not expected_graph_set or not isinstance(actual_graph_set, str) or not actual_graph_set:
            raise HostError("query graph-set receipt is missing")
        if actual_graph_set != expected_graph_set:
            raise HostError("query graph-set drift")
    for key in ("workspace_version", "source_signature"):
        if actual.get(key) != expected.get(key):
            raise HostError(f"query {key} drift")


def _probe_public_routes(transport: RestTransport, scope: dict[str, str]) -> dict[str, Any]:
    """Exercise only current graph-set, detail and scoped-SPARQL public contracts."""
    context = _ok(transport.request("GET", f"/api/ontologies/{scope['ontology_id']}/modeling-context"))
    workspace = context.get("workspace")
    if not isinstance(workspace, dict):
        raise HostError("modeling context lacks workspace")
    workspace_context = _ok(
        transport.request(
            "GET", f"/api/ontologies/{scope['ontology_id']}/workspace-context"
        )
    )
    if (
        workspace_context.get("ontology_id") != scope["ontology_id"]
        or workspace_context.get("state") != "ready"
    ):
        raise HostError("ontology workspace context is not ready and exact")
    graph_set_id = workspace_context.get("default_graph_set_id")
    if not isinstance(graph_set_id, str) or not graph_set_id:
        raise HostError("ontology workspace context lacks default graph set")
    graph_set = _ok(transport.request("GET", f"/api/semantic/graph-sets/{graph_set_id}"))
    if graph_set.get("id") != graph_set_id or graph_set.get("status") != "active" or not isinstance(graph_set.get("source_signature"), str):
        raise HostError("graph-set description is not active and exact")
    reasoning = _ok(transport.request("POST", f"/api/semantic/graph-sets/{graph_set_id}/reasoning-runs", {"tasks": ["consistency"], "persist_result_graph": False}))
    reasoning_detail = _ok(transport.request("GET", f"/api/semantic/reasoning-runs/{_required_str(reasoning, 'run_id')}"))
    _terminal(reasoning_detail, "reasoning")
    if reasoning_detail.get("consistent") is not True or reasoning_detail.get("graph_set_id") != graph_set_id or reasoning_detail.get("source_signature") != graph_set["source_signature"]:
        raise HostError("reasoning detail is inconsistent or stale")
    validation = _ok(transport.request("POST", f"/api/semantic/graph-sets/{graph_set_id}/validation-runs", {"persist_report_graph": False}))
    validation_detail = _ok(transport.request("GET", f"/api/semantic/validation-runs/{_required_str(validation, 'run_id')}"))
    _terminal(validation_detail, "validation")
    if validation_detail.get("conforms") is not True or validation_detail.get("graph_set_id") != graph_set_id or validation_detail.get("source_signature") != graph_set["source_signature"]:
        raise HostError("validation detail is non-conforming or stale")
    probe = _ok(transport.request("POST", "/api/semantic/sparql:query", {"project_id": scope["project_id"], "scope_mode": "ontologies", "ontology_ids": [scope["ontology_id"]], "query": "ASK WHERE { ?s ?p ?o }", "timeout_seconds": 10, "result_limit": 1}))
    query_scope = _scope_from_response(probe, scope["ontology_id"])
    if query_scope["workspace_version"] != workspace.get("workspace_version") or query_scope["source_signature"] != graph_set["source_signature"]:
        raise HostError("base scoped query scope does not match workspace/graph set")
    query_scope["graph_set_id"] = graph_set_id
    return {
        "context": context,
        "workspace_context": workspace_context,
        "graph_set": graph_set,
        "reasoning": reasoning_detail,
        "validation": validation_detail,
        "probe": probe,
        "scope": query_scope,
    }


def _execute_frozen_assertions(transport: RestTransport, scope: dict[str, str], queries: dict[str, str], package: dict[str, Any], expected_scope: dict[str, Any], role_map: dict[str, dict[str, str]] | None = None) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    absence_ids = {entry["id"] for entry in package["closed_snapshot_absence_assertions"]}
    for assertion_id, query in queries.items():
        response = _ok(transport.request("POST", "/api/semantic/sparql:query", {"project_id": scope["project_id"], "scope_mode": "ontologies", "ontology_ids": [scope["ontology_id"]], "query": query, "timeout_seconds": 10, "result_limit": 1}))
        query_scope = _scope_from_response(response, scope["ontology_id"])
        _require_scope_matches(query_scope, expected_scope, scope["ontology_id"])
        answer = response.get("result", {}).get("boolean") if isinstance(response.get("result"), dict) else None
        if answer is not (assertion_id in absence_ids):
            raise HostError(f"assertion {assertion_id} did not have its required public result")
        results[assertion_id] = {"result": response.get("result"), "scope": query_scope, "query_sha256": candidate_hash(query)}
    # Producer claims are retained as non-authoritative query hints for the Judge.  The Host must
    # never map them to hidden semantics or derive an L1 verdict from them.
    return results


def _snapshot_query() -> str:
    return ADDITIONAL_READ_QUERIES["rdf-snapshot"]


def _canonical_binding_row(row: object) -> dict[str, Any]:
    """Retain only deterministic SPARQL binding values in a canonical RDF evidence row."""
    if not isinstance(row, dict) or not row:
        raise HostError("RDF snapshot contains an invalid row")
    result: dict[str, Any] = {}
    for name, value in sorted(row.items()):
        if not isinstance(name, str) or not isinstance(value, dict):
            raise HostError("RDF snapshot binding is invalid")
        term_type, term_value = value.get("type"), value.get("value")
        if term_type not in {"uri", "bnode", "literal"} or not isinstance(term_value, str):
            raise HostError("RDF snapshot binding lacks a canonical term")
        result[name] = {
            key: value[key]
            for key in ("type", "value", "datatype", "xml:lang")
            if key in value and isinstance(value[key], str)
        }
    return result


def _complete_rdf_snapshot(
    transport: RestTransport, scope: dict[str, str], expected_scope: dict[str, Any]
) -> dict[str, Any]:
    """Read the one Host-owned complete RDF projection below its frozen scenario ceiling."""
    response = _ok(transport.request("POST", "/api/semantic/sparql:query", {
        "project_id": scope["project_id"],
        "scope_mode": "ontologies",
        "ontology_ids": [scope["ontology_id"]],
        "query": _snapshot_query(),
        "timeout_seconds": 10,
        "result_limit": SNAPSHOT_ROW_CEILING,
    }))
    actual_scope = _scope_from_response(response, scope["ontology_id"])
    _require_scope_matches(actual_scope, expected_scope, scope["ontology_id"])
    result = response.get("result")
    bindings = result.get("bindings") if isinstance(result, dict) else None
    if not isinstance(bindings, list):
        raise HostError("RDF snapshot lacks SELECT bindings")
    # A response at the configured bound is not a proof of completeness even if it omits a
    # truncation bit; a scenario needs an unambiguous strict-below-bound receipt.
    if len(bindings) >= SNAPSHOT_ROW_CEILING:
        raise HostError("RDF snapshot reached the scenario ceiling without complete proof")
    rows = [_canonical_binding_row(row) for row in bindings]
    row_hashes = [hashlib.sha256(canonical_json(row)).hexdigest() for row in rows]
    return {
        "query_id": "rdf-snapshot",
        "query_sha256": candidate_hash(_snapshot_query()),
        "scope": actual_scope,
        "row_count": len(rows),
        "ceiling": SNAPSHOT_ROW_CEILING,
        "rows": rows,
        "row_sha256": row_hashes,
    }


def _seal_public_evidence_bundle(
    transport: RestTransport,
    *,
    root: Path,
    state: dict[str, Any],
    semantic_package: dict[str, Any],
    producer: dict[str, Any],
) -> dict[str, Any]:
    """Seal only public, paired facts; no hidden answer or Host semantic conclusion enters it."""
    verification = producer.get("verification")
    if not isinstance(verification, dict) or not isinstance(verification.get("scope"), dict):
        raise HostError("Producer verification scope is missing")
    snapshot = _complete_rdf_snapshot(transport, state["scope"], verification["scope"])
    bundle_root = root / "public-evidence"
    if bundle_root.exists():
        raise HostError("public evidence bundle already exists")
    bundle_root.mkdir()
    producer_claims = producer.get("producer_claim_query_evidence")
    if not isinstance(producer_claims, dict):
        raise HostError("Producer claim query evidence is missing")
    public_bundle = {
        "bundle_version": 1,
        "contract_version": CONTRACT_VERSION,
        "run_id": state["run_id"],
        "scope": state["scope"],
        "source_signature": snapshot["scope"]["source_signature"],
        "workspace_version": snapshot["scope"]["workspace_version"],
        "semantic_package_sha256": candidate_hash(semantic_package),
        "run_manifest_sha256": state["run_manifest_sha256"],
        "base_dry_run": producer["base_dry_run"] if "base_dry_run" in producer else state["base_dry_run"],
        "principal_dry_run": producer["principal_dry_run"],
        "principal_apply": producer["principal_apply"],
        "validation": verification["validation"],
        "reasoning": verification["reasoning"],
        "freshness": snapshot["scope"],
        # Claims and their query receipts are a Judge hint only.  They are deliberately not an
        # answer map and no Host code reads them to decide a semantic CQ.
        "producer_claim_query_evidence": producer_claims,
    }
    _write_json(bundle_root / "bundle.json", public_bundle)
    # The sealed Agent package is public evidence, not a Host interpretation.  Keeping the exact
    # canonical copy lets a Judge relate dry/apply receipts to the package hash without inheriting
    # Agent history or any hidden contract.
    _write_json(bundle_root / "semantic-package.json", semantic_package)
    _write_json(bundle_root / "rdf-snapshot.json", snapshot)
    files = [
        {"id": f"{state['run_id']}:bundle", "path": "bundle.json", "sha256": _sha256_file(bundle_root / "bundle.json")},
        {"id": f"{state['run_id']}:semantic-package", "path": "semantic-package.json", "sha256": _sha256_file(bundle_root / "semantic-package.json")},
        {"id": f"{state['run_id']}:snapshot", "path": "rdf-snapshot.json", "sha256": _sha256_file(bundle_root / "rdf-snapshot.json")},
        *[
            {"id": f"{state['run_id']}:snapshot-row-{index}", "path": "rdf-snapshot.json", "sha256": row_hash}
            for index, row_hash in enumerate(snapshot["row_sha256"])
        ],
    ]
    manifest = {"manifest_version": 1, "run_id": state["run_id"], "scope": state["scope"], "source_signature": snapshot["scope"]["source_signature"], "files": files}
    _write_json(bundle_root / "evidence-manifest.json", manifest)
    return {
        "directory": str(bundle_root),
        "manifest_sha256": _sha256_file(bundle_root / "evidence-manifest.json"),
        "bundle_sha256": _sha256_file(bundle_root / "bundle.json"),
        "semantic_package_sha256": _sha256_file(bundle_root / "semantic-package.json"),
        "snapshot_sha256": _sha256_file(bundle_root / "rdf-snapshot.json"),
        "source_signature": snapshot["scope"]["source_signature"],
        "workspace_version": snapshot["scope"]["workspace_version"],
        "row_count": snapshot["row_count"],
        "ceiling": SNAPSHOT_ROW_CEILING,
    }


def _copy_judge_public_sources(destination: Path, input_manifest: dict[str, Any]) -> dict[str, Any]:
    """Copy only the pre-Producer source/fixture set, never Agent output or history."""
    source_root = destination / "public-sources"
    source_root.mkdir()
    source_paths = (
        "business-fixture.md",
        *sorted(path.relative_to(AGENT_INPUT).as_posix() for path in (AGENT_INPUT / "official").glob("*.mdx")),
    )
    hashes = {entry["path"]: entry["sha256"] for entry in input_manifest["files"]}
    if not all(path in hashes for path in source_paths):
        raise HostError("pre-Producer source manifest lacks a Judge source")
    for relative in source_paths:
        source = AGENT_INPUT / relative
        target = source_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    source_manifest = {
        "manifest_version": 1,
        "pre_producer_input_manifest_sha256": _manifest_digest(input_manifest),
        "files": [{"path": path, "sha256": hashes[path]} for path in source_paths],
    }
    _write_json(destination / "public-source-manifest.json", source_manifest)
    return source_manifest


def _seal_producer_evidence_boundary(state: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    """Bind the completed Producer run to its immutable public evidence before Judge staging."""
    unsigned = {
        "receipt_version": 1,
        "run_id": state["run_id"],
        "scope": state["scope"],
        "bundle_sha256": bundle["bundle_sha256"],
        "manifest_sha256": bundle["manifest_sha256"],
        "source_signature": bundle["source_signature"],
    }
    return {**unsigned, "receipt_sha256": candidate_hash(unsigned)}


def _verify_producer_evidence_boundary(state: dict[str, Any], bundle: dict[str, Any]) -> None:
    receipt = state.get("producer_evidence_boundary")
    if not isinstance(receipt, dict) or set(receipt) != {
        "receipt_version", "run_id", "scope", "bundle_sha256", "manifest_sha256", "source_signature", "receipt_sha256"
    }:
        raise HostError("sealed Producer evidence boundary is missing")
    unsigned = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    if receipt.get("receipt_version") != 1 or receipt.get("receipt_sha256") != candidate_hash(unsigned):
        raise HostError("sealed Producer evidence boundary receipt drift")
    expected = {
        "run_id": state.get("run_id"),
        "scope": state.get("scope"),
        "bundle_sha256": bundle.get("bundle_sha256"),
        "manifest_sha256": bundle.get("manifest_sha256"),
        "source_signature": bundle.get("source_signature"),
    }
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise HostError("sealed Producer evidence boundary does not pair with this run")


def _stage_judge(root: Path, state: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    """Create a fresh Judge-only directory after Producer completion and evidence sealing."""
    stage = root / "judge-staging"
    if stage.exists() or state.get("status") != "PRODUCER_EVIDENCE_SEALED":
        raise HostError("Judge staging requires a sealed Producer evidence boundary")
    _verify_producer_evidence_boundary(state, bundle)
    if not (root / "public-evidence" / "evidence-manifest.json").is_file():
        raise HostError("Judge staging requires a sealed public evidence bundle")
    input_manifest = verify_agent_input()
    expected_input = state.get("contract_hashes", {}).get("input")
    if expected_input is not None and expected_input != _manifest_digest(input_manifest):
        raise HostError("pre-Producer public source manifest drift")
    stage.mkdir()
    _copy_judge_public_sources(stage, input_manifest)
    for name in JUDGE_REQUIRED_FILES:
        shutil.copy2(HOST_ONLY / name, stage / name)
    shutil.copytree(root / "public-evidence", stage / "public-evidence")
    acceptance = json.loads((HOST_ONLY / "acceptance-contract.json").read_text(encoding="utf-8"))
    judge_contract = {
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "run_id": state["run_id"],
        "scope": state["scope"],
        "source_signature": bundle["source_signature"],
        "pre_producer_input_manifest_sha256": _manifest_digest(input_manifest),
        "public_source_manifest_sha256": _sha256_file(stage / "public-source-manifest.json"),
        "required_cq_ids": [*acceptance["capability_questions"], *acceptance["required_regressions"]],
        "verdict_statuses": sorted(JUDGE_STATUSES),
        "verdict_schema": acceptance["judge_verdict_schema"],
        "citation_schema": {"citation": {"evidence_id": "manifest member ID", "sha256": "exact member hash"}},
        "instructions": "Decide from cited public evidence. Producer claims are non-authoritative hints.",
    }
    _write_json(stage / "judge-contract.json", judge_contract)
    manifest = _write_directory_manifest(stage, "judge-staged-manifest.json", mutable_files={"judge-verdict.json"})
    return {"directory": str(stage), "manifest_sha256": _manifest_digest(manifest), "judge_contract_sha256": _sha256_file(stage / "judge-contract.json")}


def _evidence_members(state: dict[str, Any]) -> dict[str, str]:
    public = state.get("public_evidence")
    if not isinstance(public, dict) or not isinstance(public.get("directory"), str):
        raise HostError("sealed public evidence bundle is missing")
    root = Path(public["directory"])
    manifest_path = root / "evidence-manifest.json"
    if not manifest_path.is_file() or _sha256_file(manifest_path) != public.get("manifest_sha256"):
        raise HostError("public evidence manifest drift")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("run_id") != state.get("run_id") or manifest.get("scope") != state.get("scope"):
        raise HostError("public evidence belongs to a different run or scope")
    members: dict[str, str] = {}
    for entry in manifest.get("files", []):
        if not isinstance(entry, dict) or set(entry) != {"id", "path", "sha256"}:
            raise HostError("public evidence member is invalid")
        member_id, path, digest = entry["id"], entry["path"], entry["sha256"]
        if not isinstance(member_id, str) or not isinstance(path, str) or not isinstance(digest, str) or member_id in members:
            raise HostError("public evidence member is invalid")
        if path != "rdf-snapshot.json" and _sha256_file(root / path) != digest:
            raise HostError("public evidence file hash drift")
        members[member_id] = digest
    extensions = state.get("additional_evidence", [])
    if not isinstance(extensions, list):
        raise HostError("additional evidence receipt is invalid")
    for extension in extensions:
        if not isinstance(extension, dict) or set(extension) != {"id", "sha256", "source_signature"} or extension["source_signature"] != public.get("source_signature"):
            raise HostError("additional evidence is stale or malformed")
        if extension["id"] in members:
            raise HostError("additional evidence ID is duplicated")
        members[extension["id"]] = extension["sha256"]
    return members


def _load_exact_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HostError(f"{label} is missing or invalid") from exc
    if not isinstance(value, dict):
        raise HostError(f"{label} must be an object")
    return value


def _validate_citations(value: object, members: dict[str, str]) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise HostError("verdict requires one or more immutable evidence citations")
    result: list[dict[str, str]] = []
    for citation in value:
        if not isinstance(citation, dict) or set(citation) != {"evidence_id", "sha256"}:
            raise HostError("verdict citation has an invalid shape")
        evidence_id, digest = citation["evidence_id"], citation["sha256"]
        if not isinstance(evidence_id, str) or not isinstance(digest, str) or members.get(evidence_id) != digest:
            raise HostError("verdict citation is invented, stale, cross-run, or not a bundle member")
        result.append({"evidence_id": evidence_id, "sha256": digest})
    if len({(item["evidence_id"], item["sha256"]) for item in result}) != len(result):
        raise HostError("verdict repeats a citation")
    return result


def _required_judge_ids() -> list[str]:
    acceptance = _load_exact_object(HOST_ONLY / "acceptance-contract.json", "acceptance contract")
    if acceptance.get("contract_version") != CONTRACT_VERSION:
        raise HostError("acceptance contract version drift")
    ids = [*acceptance.get("capability_questions", []), *acceptance.get("required_regressions", [])]
    if not ids or not all(isinstance(value, str) and value for value in ids) or len(ids) != len(set(ids)):
        raise HostError("acceptance contract CQ IDs are invalid")
    return ids


def _validate_judge_verdict(state: dict[str, Any], verdict: object) -> dict[str, Any]:
    if not isinstance(verdict, dict) or set(verdict) != {
        "schema_version", "run_id", "scope", "source_signature", "answers", "additional_evidence_hashes"
    }:
        raise HostError("Judge verdict has an invalid schema")
    public = state.get("public_evidence", {})
    if verdict.get("schema_version") != 1 or verdict.get("run_id") != state.get("run_id") or verdict.get("scope") != state.get("scope") or verdict.get("source_signature") != public.get("source_signature"):
        raise HostError("Judge verdict run identity, scope, or source signature mismatch")
    members = _evidence_members(state)
    acceptance = _load_exact_object(HOST_ONLY / "acceptance-contract.json", "acceptance contract")
    schema = acceptance.get("judge_verdict_schema")
    if not isinstance(schema, dict):
        raise HostError("Judge verdict schema contract is invalid")
    answer_keys = schema.get("answer_exact_keys")
    failure_classes = schema.get("failure_classifications")
    if not isinstance(answer_keys, list) or not all(isinstance(key, str) for key in answer_keys) or len(answer_keys) != len(set(answer_keys)) or not isinstance(failure_classes, list) or not all(isinstance(value, str) and value for value in failure_classes):
        raise HostError("Judge verdict schema contract is invalid")
    expected_answer_keys = set(answer_keys)
    allowed_failure_classes = set(failure_classes)
    answers = verdict.get("answers")
    if not isinstance(answers, list) or len(answers) != len(_required_judge_ids()):
        raise HostError("Judge verdict must answer every required CQ exactly once")
    normalized: list[dict[str, Any]] = []
    for answer in answers:
        if not isinstance(answer, dict) or set(answer) != expected_answer_keys:
            raise HostError("Judge answer has an invalid schema")
        cq_id, status = answer["cq_id"], answer["status"]
        if not isinstance(cq_id, str) or status not in JUDGE_STATUSES:
            raise HostError("Judge answer has an invalid CQ ID or status")
        conclusion = answer.get("conclusion")
        missing = answer.get("missing_or_contradictory_evidence")
        classification = answer.get("failure_classification")
        if not isinstance(conclusion, str) or not conclusion.strip() or not isinstance(missing, list) or not all(isinstance(value, str) for value in missing):
            raise HostError("Judge answer conclusion or evidence notes are invalid")
        if status == "PASS":
            if classification is not None:
                raise HostError("PASS Judge answer must not carry a failure classification")
        elif classification not in allowed_failure_classes:
            raise HostError("non-PASS Judge answer requires an allowed failure classification")
        normalized.append({
            "cq_id": cq_id,
            "status": status,
            "conclusion": conclusion,
            "missing_or_contradictory_evidence": list(missing),
            "failure_classification": classification,
            "citations": _validate_citations(answer["citations"], members),
        })
    if sorted(answer["cq_id"] for answer in normalized) != sorted(_required_judge_ids()):
        raise HostError("Judge verdict CQ IDs do not exactly match the frozen contract")
    additional = verdict.get("additional_evidence_hashes")
    if not isinstance(additional, list) or not all(isinstance(value, str) for value in additional):
        raise HostError("Judge additional evidence declaration is invalid")
    extension_hashes = {
        item["sha256"] for item in state.get("additional_evidence", []) if isinstance(item, dict)
    }
    if set(additional) - extension_hashes or len(additional) != len(set(additional)):
        raise HostError("Judge additional evidence is not an append-only Host receipt")
    return {**verdict, "answers": normalized}


def _validate_adjudication(state: dict[str, Any], adjudication: object) -> dict[str, str]:
    if not isinstance(adjudication, dict) or set(adjudication) != {"run_id", "decision"}:
        raise HostError("main-Agent adjudication has an invalid schema")
    if adjudication.get("run_id") != state.get("run_id") or adjudication.get("decision") not in {"accept", "reject"}:
        raise HostError("main-Agent adjudication does not pair with this Judge run")
    return {"run_id": adjudication["run_id"], "decision": adjudication["decision"]}


def _stage_consumer(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    """Give L2 only public evidence and question IDs; hidden Judge contracts never cross this boundary."""
    stage = root / "consumer-staging"
    if stage.exists():
        raise HostError("Consumer staging already exists")
    stage.mkdir()
    shutil.copytree(root / "public-evidence", stage / "public-evidence")
    contract = {
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "run_id": state["run_id"],
        "scope": state["scope"],
        "source_signature": state["public_evidence"]["source_signature"],
        "question_ids": _required_judge_ids(),
        "read_only": True,
        "citation_schema": {"citation": {"evidence_id": "manifest member ID", "sha256": "exact member hash"}},
    }
    _write_json(stage / "consumer-contract.json", contract)
    manifest = _write_directory_manifest(stage, "consumer-staged-manifest.json", mutable_files={"consumer-result.json"})
    return {"directory": str(stage), "manifest_sha256": _manifest_digest(manifest), "consumer_contract_sha256": _sha256_file(stage / "consumer-contract.json")}


def _terminal_cleanup(
    transport: RestTransport, state_path: Path, state: dict[str, Any], *, cause: str, terminal: str
) -> dict[str, Any]:
    cleanup = _cleanup_owned(transport, state["scope"]["project_id"])
    status = terminal if cleanup["success"] is True else "CLEANUP_FAILED"
    state.update({"status": status, "primary_cause": cause, "cleanup": cleanup})
    receipt = {"run_id": state["run_id"], "status": status, "primary_cause": cause, "cleanup": cleanup}
    if "judge_semantic_outcome" in state:
        receipt["judge_semantic_outcome"] = state["judge_semantic_outcome"]
    if "judge_no_verdict" in state:
        receipt["judge_no_verdict"] = state["judge_no_verdict"]
    _write_json(state_path, state)
    _write_json(state_path.parent / "terminal-receipt.json", receipt)
    return receipt


def finalize_judge(
    transport: RestTransport,
    *,
    state_path: Path,
    verdict: object,
    adjudication: object,
    attempt_ledger: AttemptLedger | None = None,
    execute_guarded: bool = False,
) -> dict[str, Any]:
    """Mechanically accept a paired Judge verdict; semantic interpretation remains entirely external."""
    if execute_guarded is not True:
        raise HostError("refusing Judge finalization without --execute-guarded")
    state = _load_state(state_path)
    if state.get("status") != "AWAITING_JUDGE":
        raise HostError("finalize requires an AWAITING_JUDGE state")
    try:
        normalized = _validate_judge_verdict(state, verdict)
        decision = _validate_adjudication(state, adjudication)
    except Exception as exc:
        _terminal_cleanup(transport, state_path, state, cause=f"invalid_judge_verdict:{exc}", terminal="FAILED")
        raise
    all_pass = all(answer["status"] == "PASS" for answer in normalized["answers"])
    semantic_outcome = "PASS" if all_pass else (
        "FAIL" if any(answer["status"] == "FAIL" for answer in normalized["answers"]) else "INCONCLUSIVE"
    )
    # Persist the normalized verdict before any terminal cleanup.  These fields are evidence, not a
    # Host interpretation of the Judge's conclusion.
    state.update({"judge_verdict": normalized, "judge_semantic_outcome": semantic_outcome})
    _write_json(state_path, state)
    if all_pass and decision["decision"] == "accept":
        authorization: dict[str, Any] | None = None
        if attempt_ledger is not None:
            authorization = {
                "event": "l1_pass_authorized",
                "run_id": state["run_id"],
                "scope": state["scope"],
                "judge_verdict_sha256": candidate_hash(normalized),
                "contract_version": CONTRACT_VERSION,
            }
            attempt_ledger.append_l1_pass_authorized(authorization)
        consumer = _stage_consumer(state_path.parent, state)
        state.update({"status": "AWAITING_L2_CONSUMER", "judge_verdict": normalized, "main_agent_adjudication": decision, "l1_pass_authorization": authorization, "consumer": consumer, "cleanup": None})
        _write_json(state_path, state)
        return {"status": "AWAITING_L2_CONSUMER", "judge_verdict": normalized, "consumer": consumer}
    cause = "judge_non_pass" if not all_pass else "main_agent_rejected_judge_verdict"
    return _terminal_cleanup(transport, state_path, state, cause=cause, terminal="FAILED")


def abort_judge(
    transport: RestTransport, *, state_path: Path, reason: str, execute_guarded: bool = False
) -> dict[str, Any]:
    """Paired, idempotent crash/timeout exit.  It never fabricates a verdict."""
    if execute_guarded is not True:
        raise HostError("refusing Judge abort without --execute-guarded")
    state = _load_state(state_path)
    if state.get("status") in {"CLEANED", "FAILED", "CLEANUP_FAILED"}:
        return _load_exact_object(state_path.parent / "terminal-receipt.json", "Judge abort receipt")
    if state.get("status") != "AWAITING_JUDGE" or not isinstance(reason, str) or not reason:
        raise HostError("abort-judge requires an AWAITING_JUDGE state and a primary cause")
    state.update({
        "judge_semantic_outcome": "INCONCLUSIVE",
        "judge_no_verdict": {
            "receipt_version": 1,
            "run_id": state["run_id"],
            "scope": state["scope"],
            "semantic_outcome": "INCONCLUSIVE",
            "no_verdict": True,
            "primary_cause": reason,
        },
    })
    _write_json(state_path, state)
    return _terminal_cleanup(transport, state_path, state, cause=f"judge_inconclusive:{reason}", terminal="CLEANED")


def append_additional_read_evidence(
    transport: RestTransport, *, state_path: Path, request_contract: object, execute_guarded: bool = False
) -> dict[str, Any]:
    """Host-owned allowlisted read-only queries only; callers cannot inject SPARQL text or scope."""
    if execute_guarded is not True:
        raise HostError("refusing additional read without --execute-guarded")
    state = _load_state(state_path)
    if state.get("status") not in {"AWAITING_JUDGE", "AWAITING_L2_CONSUMER"}:
        raise HostError("additional read requires a retained Judge or Consumer scope")
    if not isinstance(request_contract, dict) or set(request_contract) != {"query_id"}:
        raise HostError("additional read contract permits only an allowlisted query_id")
    query_id = request_contract.get("query_id")
    if query_id not in ADDITIONAL_READ_QUERIES:
        raise HostError("additional read query is not allowlisted or is not read-only")
    public = state.get("public_evidence", {})
    response = _ok(transport.request("POST", "/api/semantic/sparql:query", {
        "project_id": state["scope"]["project_id"],
        "scope_mode": "ontologies",
        "ontology_ids": [state["scope"]["ontology_id"]],
        "query": ADDITIONAL_READ_QUERIES[query_id],
        "timeout_seconds": 10,
        "result_limit": SNAPSHOT_ROW_CEILING if query_id == "rdf-snapshot" else 1,
    }))
    actual = _scope_from_response(response, state["scope"]["ontology_id"])
    if actual.get("source_signature") != public.get("source_signature") or actual.get("workspace_version") != public.get("workspace_version"):
        raise HostError("additional read scope or source signature is stale")
    extension = {
        "id": f"{state['run_id']}:additional-{len(state.get('additional_evidence', []))}",
        "sha256": candidate_hash({"query_id": query_id, "response": response}),
        "source_signature": actual["source_signature"],
    }
    extension_path = Path(public["directory"]) / "additional-evidence.jsonl"
    with extension_path.open("ab") as stream:
        stream.write(canonical_json({"query_id": query_id, "response": response, **extension}) + b"\n")
    state.setdefault("additional_evidence", []).append(extension)
    _write_json(state_path, state)
    return extension


def _validate_consumer_result(state: dict[str, Any], value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"schema_version", "run_id", "scope", "source_signature", "read_only", "citations"}:
        raise HostError("Consumer result has an invalid schema")
    if value.get("schema_version") != 1 or value.get("run_id") != state.get("run_id") or value.get("scope") != state.get("scope") or value.get("source_signature") != state.get("public_evidence", {}).get("source_signature") or value.get("read_only") is not True:
        raise HostError("Consumer result pairing or read-only receipt is invalid")
    return {**value, "citations": _validate_citations(value.get("citations"), _evidence_members(state))}


def complete_consumer(
    transport: RestTransport, *, state_path: Path, result: object, execute_guarded: bool = False
) -> dict[str, Any]:
    if execute_guarded is not True:
        raise HostError("refusing Consumer completion without --execute-guarded")
    state = _load_state(state_path)
    if state.get("status") in {"CLEANED", "FAILED", "CLEANUP_FAILED"}:
        return _load_exact_object(state_path.parent / "terminal-receipt.json", "Consumer completion receipt")
    if state.get("status") != "AWAITING_L2_CONSUMER":
        raise HostError("complete-consumer requires an AWAITING_L2_CONSUMER state")
    try:
        normalized = _validate_consumer_result(state, result)
    except Exception as exc:
        _terminal_cleanup(transport, state_path, state, cause=f"invalid_consumer_result:{exc}", terminal="FAILED")
        raise
    state["consumer_result"] = normalized
    return _terminal_cleanup(transport, state_path, state, cause="consumer_completed", terminal="CLEANED")


def abort_consumer(
    transport: RestTransport, *, state_path: Path, reason: str, execute_guarded: bool = False
) -> dict[str, Any]:
    if execute_guarded is not True:
        raise HostError("refusing Consumer abort without --execute-guarded")
    state = _load_state(state_path)
    if state.get("status") in {"CLEANED", "FAILED", "CLEANUP_FAILED"}:
        return _load_exact_object(state_path.parent / "terminal-receipt.json", "Consumer abort receipt")
    if state.get("status") != "AWAITING_L2_CONSUMER" or not isinstance(reason, str) or not reason:
        raise HostError("abort-consumer requires an AWAITING_L2_CONSUMER state and a primary cause")
    return _terminal_cleanup(transport, state_path, state, cause=f"consumer_aborted:{reason}", terminal="CLEANED")


def _cleanup_owned(transport: RestTransport, project_id: str | None) -> dict[str, Any]:
    if project_id is None:
        return {"attempted": False, "success": True}
    try:
        _ok(transport.request("DELETE", f"/api/projects/{project_id}"))
        return {"attempted": True, "success": True, "project_id": project_id}
    except Exception as exc:
        return {"attempted": True, "success": False, "project_id": project_id, "error": str(exc)}


def main() -> int:
    """Run a named guarded phase; no phase launches an Agent itself."""
    parser = argparse.ArgumentParser(description="Execute guarded M7 Host phases.")
    parser.add_argument(
        "mode",
        choices=(
            "prepare", "continue", "finalize", "abort-judge", "complete-consumer",
            "abort-consumer", "cleanup",
        ),
    )
    parser.add_argument("--execute-guarded", action="store_true")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key-env", default="M7_API_KEY")
    parser.add_argument("--run-id")
    parser.add_argument("--runtime-root", type=Path, default=SCENARIO_ROOT / "runtime")
    parser.add_argument("--state", type=Path)
    parser.add_argument("--verdict", type=Path)
    parser.add_argument("--adjudication", type=Path)
    parser.add_argument("--consumer-result", type=Path)
    parser.add_argument("--reason")
    parser.add_argument("--attempt-ledger", type=Path)
    args = parser.parse_args()
    if not args.execute_guarded:
        parser.error("--execute-guarded is required")
    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        parser.error(f"{args.api_key_env} must be set only in the Host environment")
    transport = UrllibRestTransport(args.base_url, api_key)
    if args.mode == "prepare":
        if not args.run_id:
            parser.error("prepare requires --run-id")
        result = prepare_guarded(transport, run_id=args.run_id, runtime_root=args.runtime_root, execute_guarded=True)
    elif args.mode == "continue":
        if not args.state:
            parser.error("continue requires --state; Host-generated proof queries are read only from the sealed package")
        result = continue_guarded(transport, state_path=args.state, execute_guarded=True)
    elif args.mode == "finalize":
        if not args.state or not args.verdict or not args.adjudication:
            parser.error("finalize requires --state --verdict and --adjudication")
        result = finalize_judge(
            transport,
            state_path=args.state,
            verdict=_load_exact_object(args.verdict, "Judge verdict"),
            adjudication=_load_exact_object(args.adjudication, "main-Agent adjudication"),
            attempt_ledger=AttemptLedger(args.attempt_ledger) if args.attempt_ledger else None,
            execute_guarded=True,
        )
    elif args.mode == "abort-judge":
        if not args.state or not args.reason:
            parser.error("abort-judge requires --state and --reason")
        result = abort_judge(transport, state_path=args.state, reason=args.reason, execute_guarded=True)
    elif args.mode == "complete-consumer":
        if not args.state or not args.consumer_result:
            parser.error("complete-consumer requires --state and --consumer-result")
        result = complete_consumer(
            transport,
            state_path=args.state,
            result=_load_exact_object(args.consumer_result, "Consumer result"),
            execute_guarded=True,
        )
    elif args.mode == "abort-consumer":
        if not args.state or not args.reason:
            parser.error("abort-consumer requires --state and --reason")
        result = abort_consumer(transport, state_path=args.state, reason=args.reason, execute_guarded=True)
    else:
        if not args.state:
            parser.error("cleanup requires --state")
        result = cleanup_guarded(transport, state_path=args.state, execute_guarded=True)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
