#!/usr/bin/env python3
"""Tester-owned, data-driven formal Modeling Batch acceptance mutation runner.

The runner deliberately contains no ontology, SPARQL query, expected row or pass/fail answer. Testers
provide those in a JSON spec; this script evaluates their declared assertions and retains expected and
actual JSON for independent review.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import uuid
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
SCENARIO_ROOT = Path(__file__).resolve().parents[1]
STABLE_SEED_ITEMS_FILES = [
    "runtime/runs/m3-session-cycle5-rerun-20260726/work/requests/schema-batch.json",
    "runtime/runs/m3-session-cycle5-rerun-20260726/work/requests/fixture-batch.json",
]
MAX_SEED_FILE_BYTES = 8 * 1024 * 1024


class AcceptanceSpecError(ValueError):
    """A tester-provided mutation plan is incomplete or unsafe."""


EXPECTED_VARIANTS = {"baseline", "decoy", "remove", "sentinel_replace"}
ASSERTION_KEYS = {"http_status", "row_count", "bindings", "predicates", "same_row_identity"}
SEMANTIC_OBSERVATION_KEYS = (
    "http_status",
    "row_count",
    "bindings",
    "predicates",
    "same_row_identity",
)


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_api_key() -> str:
    for line in (REPOSITORY_ROOT / "backend" / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("ONTOLOGY_MCP_API_KEY="):
            value = line.partition("=")[2].strip().strip("\"'")
            if value:
                return value
    raise AcceptanceSpecError("backend/.env has no ONTOLOGY_MCP_API_KEY")


def validate_action(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - {"id", "items"} or set(value) != {"id", "items"}:
        raise AcceptanceSpecError(f"{label} must contain only id and items")
    if not isinstance(value["id"], str) or not value["id"] or not isinstance(value["items"], list):
        raise AcceptanceSpecError(f"{label} has invalid id or items")
    return value


def validate_spec(value: object, *, require_role_count: int = 9) -> dict[str, Any]:
    required = {"seed_actions", "orthogonal_decoy_actions", "roles", "queries"}
    optional = {"project", "ontology", "require_role_count", "seed_items_files"}
    if not isinstance(value, dict) or set(value) - (required | optional) or not required <= set(value):
        raise AcceptanceSpecError("spec has unsupported or missing keys")
    for label in ("seed_actions", "orthogonal_decoy_actions"):
        if not isinstance(value[label], list):
            raise AcceptanceSpecError(f"{label} must be a list")
        for index, action in enumerate(value[label]):
            validate_action(action, f"{label}[{index}]")
    if "seed_items_files" in value and (
        not isinstance(value["seed_items_files"], list)
        or any(not isinstance(item, str) or not item for item in value["seed_items_files"])
    ):
        raise AcceptanceSpecError("seed_items_files must be a list of non-empty scenario-relative paths")
    roles = value["roles"]
    count = int(value.get("require_role_count", require_role_count))
    if not isinstance(roles, list) or len(roles) != count:
        raise AcceptanceSpecError(f"roles must contain exactly {count} tester-defined entries")
    identifiers: set[str] = set()
    for index, role in enumerate(roles):
        if not isinstance(role, dict) or set(role) != {"id", "remove", "sentinel_replace"}:
            raise AcceptanceSpecError(f"roles[{index}] must contain id, remove and sentinel_replace")
        if not isinstance(role["id"], str) or not role["id"] or role["id"] in identifiers:
            raise AcceptanceSpecError("role IDs must be unique non-empty strings")
        identifiers.add(role["id"])
        validate_action(role["remove"], f"roles[{index}].remove")
        validate_action(role["sentinel_replace"], f"roles[{index}].sentinel_replace")
    if not isinstance(value["queries"], list) or not value["queries"]:
        raise AcceptanceSpecError("queries must be a non-empty list")
    for index, query in enumerate(value["queries"]):
        if not isinstance(query, dict) or set(query) != {"id", "body", "same_row_identity", "expected"}:
            raise AcceptanceSpecError(f"queries[{index}] has unsupported keys")
        if not isinstance(query.get("id"), str) or not isinstance(query.get("body"), dict):
            raise AcceptanceSpecError(f"queries[{index}] needs id and SPARQL body")
        if not isinstance(query.get("same_row_identity", []), list) or not all(
            isinstance(name, str) for name in query.get("same_row_identity", [])
        ):
            raise AcceptanceSpecError(f"queries[{index}].same_row_identity must be string names")
        expected = query["expected"]
        if not isinstance(expected, dict) or set(expected) != EXPECTED_VARIANTS:
            raise AcceptanceSpecError(f"queries[{index}].expected must declare baseline, decoy, remove and sentinel_replace")
        validate_assertion(expected["baseline"], f"queries[{index}].expected.baseline")
        if expected["decoy"] != {"same_as_baseline": True}:
            raise AcceptanceSpecError(f"queries[{index}].expected.decoy must require same_as_baseline")
        for mutation in ("remove", "sentinel_replace"):
            mutation_expected = expected[mutation]
            if not isinstance(mutation_expected, dict) or mutation_expected.get("break") is not True:
                raise AcceptanceSpecError(f"queries[{index}].expected.{mutation} must require break=true")
            validate_assertion(
                {key: item for key, item in mutation_expected.items() if key != "break"},
                f"queries[{index}].expected.{mutation}",
                allow_empty=True,
            )
    return value


def load_seed_items_files(spec: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, object]]]:
    actions: list[dict[str, Any]] = []
    imports: list[dict[str, object]] = []
    for index, relative_name in enumerate(spec.get("seed_items_files", []), start=1):
        relative_path = Path(relative_name)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise AcceptanceSpecError("seed_items_files may not escape the M3 scenario directory")
        source = (SCENARIO_ROOT / relative_path).resolve()
        try:
            source.relative_to(SCENARIO_ROOT.resolve())
            raw = source.read_bytes()
        except OSError as error:
            raise AcceptanceSpecError(f"cannot read seed items file: {relative_name}") from error
        if len(raw) > MAX_SEED_FILE_BYTES:
            raise AcceptanceSpecError(f"seed items file exceeds {MAX_SEED_FILE_BYTES} bytes: {relative_name}")
        try:
            batch = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AcceptanceSpecError(f"seed items file is not UTF-8 JSON: {relative_name}") from error
        if not isinstance(batch, dict) or not isinstance(batch.get("items"), list):
            raise AcceptanceSpecError(f"seed items file lacks a Modeling Batch items list: {relative_name}")
        items = json.loads(canonical_json(batch["items"]))
        if not all(isinstance(item, dict) for item in items):
            raise AcceptanceSpecError(f"seed items file has a non-object Modeling Item: {relative_name}")
        for item in items:
            # These source IDs belong to Cycle5's Project.  A fresh acceptance Project may not import
            # them; the semantic Modeling Item payload and its internal item_ref graph stay intact.
            item["evidence_reference_ids"] = []
            item["evidence"] = []
            item["competency_question_ids"] = []
        action = {"id": f"seed-file-{index}-{source.stem}", "items": items}
        actions.append(validate_action(action, f"seed_items_files[{index - 1}]"))
        imports.append(
            {
                "source": relative_path.as_posix(),
                "source_sha256": sha256_bytes(raw),
                "item_count": len(items),
                "normalization": "cleared project-bound evidence and competency-question references",
            }
        )
    return actions, imports


def starter_spec() -> dict[str, object]:
    """Generate a tester-owned shell without business queries, answers or role mappings."""
    return {
        "seed_items_files": STABLE_SEED_ITEMS_FILES,
        "seed_actions": [],
        "orthogonal_decoy_actions": [],
        "roles": [],
        "queries": [],
    }


def inspect_seed_items_files(relative_names: list[str]) -> list[dict[str, object]]:
    """Return a mechanical item inventory; never select roles, queries or assertions."""
    actions, imports = load_seed_items_files({"seed_items_files": relative_names})
    result: list[dict[str, object]] = []
    for action, imported in zip(actions, imports, strict=True):
        items = []
        for index, item in enumerate(action["items"]):
            payload = item.get("payload") if isinstance(item, dict) else None
            items.append(
                {
                    "index": index,
                    "ref": item.get("client_item_id") if isinstance(item, dict) else None,
                    "type": item.get("command_kind") if isinstance(item, dict) else None,
                    "payload_summary": {
                        "keys": sorted(payload) if isinstance(payload, dict) else [],
                        "sha256": sha256_bytes(canonical_json(payload)),
                    },
                }
            )
        result.append({"source": imported["source"], "items": items})
    return result


def validate_assertion(value: object, label: str, *, allow_empty: bool = False) -> None:
    if not isinstance(value, dict) or set(value) - ASSERTION_KEYS or (not value and not allow_empty):
        raise AcceptanceSpecError(f"{label} must declare only generic result assertions")
    if "http_status" in value and not isinstance(value["http_status"], int):
        raise AcceptanceSpecError(f"{label}.http_status must be an integer")
    if "row_count" in value and (not isinstance(value["row_count"], int) or value["row_count"] < 0):
        raise AcceptanceSpecError(f"{label}.row_count must be a non-negative integer")
    if "bindings" in value and not isinstance(value["bindings"], list):
        raise AcceptanceSpecError(f"{label}.bindings must be a list")
    if "predicates" in value and not isinstance(value["predicates"], dict):
        raise AcceptanceSpecError(f"{label}.predicates must be an object")
    if "same_row_identity" in value and not isinstance(value["same_row_identity"], list):
        raise AcceptanceSpecError(f"{label}.same_row_identity must be a list")


def expand(value: object, context: dict[str, str]) -> object:
    if isinstance(value, str):
        return context.get(value[2:-1], value) if value.startswith("${") and value.endswith("}") else value
    if isinstance(value, list):
        return [expand(item, context) for item in value]
    if isinstance(value, dict):
        return {key: expand(item, context) for key, item in value.items()}
    return value


def cell_value(value: object) -> object:
    return value.get("value") if isinstance(value, dict) and "value" in value else value


def same_row_identity(body: object, names: list[str]) -> list[dict[str, object]]:
    if not isinstance(body, dict):
        return []
    bindings = body.get("results", {}).get("bindings", [])
    if not isinstance(bindings, list):
        return []
    return [
        {"row_index": index, "identity": {name: cell_value(row.get(name)) for name in names}}
        for index, row in enumerate(bindings)
        if isinstance(row, dict)
    ]


def normalized_bindings(body: object) -> list[dict[str, object]]:
    if not isinstance(body, dict):
        return []
    bindings = body.get("results", {}).get("bindings", [])
    if not isinstance(bindings, list):
        return []
    return [
        {str(name): cell_value(value) for name, value in row.items()}
        for row in bindings
        if isinstance(row, dict)
    ]


def semantic_select_result(body: object) -> dict[str, object]:
    """Unwrap the current public SemanticSparqlQueryResponse result envelope strictly."""
    if not isinstance(body, dict) or not isinstance(body.get("result"), dict):
        raise AcceptanceSpecError("SPARQL response lacks the public result object")
    result = body["result"]
    results = result.get("results")
    bindings = results.get("bindings") if isinstance(results, dict) else None
    if not isinstance(bindings, list) or not all(isinstance(row, dict) for row in bindings):
        raise AcceptanceSpecError("SPARQL public result lacks a bindings list")
    return result


def query_observation(status: int, body: object, identity_names: list[str]) -> dict[str, object]:
    result = semantic_select_result(body)
    bindings = normalized_bindings(result)
    identities = same_row_identity(result, identity_names)
    return {
        "http_status": status,
        "body": body,
        "row_count": len(bindings),
        "bindings": bindings,
        "predicates": {
            name: [row.get(name) for row in bindings]
            for name in sorted({name for row in bindings for name in row})
        },
        "same_row_identity": [entry["identity"] for entry in identities],
    }


def semantic_observation(observation: object) -> dict[str, object]:
    if not isinstance(observation, dict) or any(key not in observation for key in SEMANTIC_OBSERVATION_KEYS):
        raise AcceptanceSpecError("query observation lacks the canonical semantic fields")
    return {key: observation[key] for key in SEMANTIC_OBSERVATION_KEYS}


def assertion_errors(observation: dict[str, object], expected: dict[str, object]) -> list[str]:
    errors: list[str] = []
    for key in ASSERTION_KEYS:
        actual = observation.get(key)
        if key == "predicates" and isinstance(expected.get(key), dict) and isinstance(actual, dict):
            actual = {name: actual.get(name) for name in expected[key]}
        if key in expected and actual != expected[key]:
            errors.append(f"{key} did not match tester expectation")
    return errors


def batch_errors(variant: dict[str, object]) -> list[str]:
    errors: list[str] = []
    for record in variant.get("batches", []):
        action_id = record["action_id"]
        dry_run = record["dry_run"].get("actual")
        applied = record.get("apply", {}).get("actual")
        if not isinstance(dry_run, dict) or dry_run.get("attempt_status") != "validated":
            errors.append(f"{action_id} dry-run was not validated")
        if not isinstance(applied, dict) or applied.get("attempt_status") != "applied":
            errors.append(f"{action_id} apply was not applied")
    return errors


def evaluate_queries(
    spec: dict[str, Any],
    baseline: dict[str, object],
    decoy: dict[str, object],
    remove: dict[str, object],
    sentinel_replace: dict[str, object],
) -> dict[str, object]:
    by_variant = {
        "baseline": baseline,
        "decoy": decoy,
        "remove": remove,
        "sentinel_replace": sentinel_replace,
    }
    errors: list[dict[str, str]] = []
    for variant_name, variant in by_variant.items():
        for error in batch_errors(variant):
            errors.append({"variant": variant_name, "query_id": "<modeling-batch>", "error": error})
    for query in spec["queries"]:
        query_id = query["id"]
        baseline = by_variant["baseline"]["queries_by_id"][query_id]
        for variant_name in EXPECTED_VARIANTS:
            record = by_variant[variant_name]["queries_by_id"][query_id]
            expected = query["expected"][variant_name]
            if variant_name == "decoy":
                variant_errors = (
                    []
                    if semantic_observation(record["actual"]) == semantic_observation(baseline["actual"])
                    else ["decoy changed baseline result"]
                )
            elif variant_name == "baseline":
                variant_errors = assertion_errors(record["actual"], expected)
            else:
                baseline_matches = not assertion_errors(record["actual"], query["expected"]["baseline"])
                variant_errors = ["mutation did not break the tester baseline assertion"] if baseline_matches else []
                variant_errors.extend(assertion_errors(record["actual"], {key: value for key, value in expected.items() if key != "break"}))
            record["expected"] = expected
            record["evaluation"] = {"passed": not variant_errors, "errors": variant_errors}
            for error in variant_errors:
                errors.append({"variant": variant_name, "query_id": query_id, "error": error})
    return {"passed": not errors, "failures": errors}


class PublicApi:
    def __init__(self, api_key: str, host: str) -> None:
        host_name, separator, port = host.partition(":")
        self.api_key = api_key
        self.host = host_name
        self.port = int(port) if separator else 80

    def call(self, method: str, path: str, body: object | None = None) -> tuple[int, object]:
        connection = http.client.HTTPConnection(self.host, self.port, timeout=60)
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = None if body is None else canonical_json(body)
        if payload is not None:
            headers["content-type"] = "application/json"
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        try:
            decoded: object = json.loads(raw.decode("utf-8")) if raw else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            decoded = {"non_json_response_sha256": sha256_bytes(raw)}
        return response.status, decoded


def require_ok(status: int, body: object, label: str) -> dict[str, Any]:
    if not 200 <= status < 300 or not isinstance(body, dict):
        raise AcceptanceSpecError(f"{label} failed with HTTP {status}")
    return body


def find_string(value: object, key: str) -> str | None:
    if isinstance(value, dict):
        if isinstance(value.get(key), str):
            return value[key]
        for item in value.values():
            found = find_string(item, key)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = find_string(item, key)
            if found:
                return found
    return None


def new_environment(api: PublicApi, spec: dict[str, Any], label: str) -> dict[str, str]:
    project_spec, ontology_spec = spec.get("project", {}), spec.get("ontology", {})
    project = require_ok(
        *api.call(
            "POST",
            "/api/projects",
            {
                "name": project_spec.get("name", f"M3 acceptance {label} {uuid.uuid4().hex[:8]}"),
                "description": project_spec.get("description", "Tester-owned temporary acceptance project."),
            },
        ),
        "create project",
    )
    project_id = str(project["id"])
    ontology = require_ok(
        *api.call(
            "POST",
            f"/api/projects/{project_id}/ontologies",
            {
                "name": ontology_spec.get("name", f"acceptance-{uuid.uuid4().hex[:8]}"),
                "description": ontology_spec.get("description", "Tester-owned acceptance ontology."),
            },
        ),
        "create ontology",
    )
    ontology_id = str(ontology["id"])
    session = require_ok(
        *api.call(
            "POST",
            f"/api/projects/{project_id}/build-sessions",
            {"client_session_id": f"acceptance-{uuid.uuid4().hex}"},
        ),
        "create build session",
    )
    session_id = str(session["id"])
    context = require_ok(*api.call("GET", f"/api/ontologies/{ontology_id}/modeling-context"), "modeling context")
    workspace_version = find_string(context, "workspace_version")
    if not workspace_version:
        raise AcceptanceSpecError("modeling context lacks workspace_version")
    lease = require_ok(
        *api.call(
            "POST",
            f"/api/build-sessions/{session_id}/ontology-leases/{ontology_id}:acquire",
            {"client_request_id": f"lease-{uuid.uuid4().hex}", "expected_session_revision": session["revision"]},
        ),
        "acquire lease",
    )
    lease_token = find_string(lease, "lease_token")
    if not lease_token:
        raise AcceptanceSpecError("lease response lacks lease_token")
    return {
        "project_id": project_id,
        "ontology_id": ontology_id,
        "session_id": session_id,
        "workspace_version": workspace_version,
        "lease_token": lease_token,
    }


def submit_action(api: PublicApi, environment: dict[str, str], action: dict[str, Any]) -> dict[str, object]:
    items = expand(action["items"], environment)
    batch_id = f"acceptance-{action['id']}-{uuid.uuid4().hex[:12]}"
    base = {
        "client_batch_id": batch_id,
        "ontology_id": environment["ontology_id"],
        "expected_workspace_version": environment["workspace_version"],
        "items": items,
    }
    dry_status, dry = api.call("POST", f"/api/build-sessions/{environment['session_id']}/modeling-batches", {**base, "idempotency_key": f"dry-{uuid.uuid4().hex}", "mode": "dry_run"})
    result: dict[str, object] = {
        "action_id": action["id"],
        "dry_run": {"http_status": dry_status, "actual": dry},
    }
    if dry_status != 200 or not isinstance(dry, dict) or dry.get("attempt_status") != "validated":
        result["apply"] = {"skipped": "platform dry-run was not validated"}
        return result
    applied_status, applied = api.call(
        "POST",
        f"/api/build-sessions/{environment['session_id']}/modeling-batches",
        {
            **base,
            "idempotency_key": f"apply-{uuid.uuid4().hex}",
            "lease_token": environment["lease_token"],
            "mode": "apply_atomic",
        },
    )
    result["apply"] = {"http_status": applied_status, "actual": applied}
    if applied_status == 200 and isinstance(applied, dict) and applied.get("attempt_status") == "applied":
        context = require_ok(
            *api.call("GET", f"/api/ontologies/{environment['ontology_id']}/modeling-context"),
            "refresh modeling context",
        )
        workspace_version = find_string(context, "workspace_version")
        if workspace_version:
            environment["workspace_version"] = workspace_version
    return result


def run_variant(
    api: PublicApi,
    spec: dict[str, Any],
    *,
    variant: str,
    actions: list[dict[str, Any]],
) -> dict[str, object]:
    environment = new_environment(api, spec, variant)
    records = [submit_action(api, environment, action) for action in spec["seed_actions"]]
    records.extend(submit_action(api, environment, action) for action in actions)
    queries: list[dict[str, object]] = []
    queries_by_id: dict[str, dict[str, object]] = {}
    for query in spec["queries"]:
        body = expand(query["body"], environment)
        status, actual = api.call("POST", "/api/semantic/sparql:query", body)
        record = {"id": query["id"], "actual": query_observation(status, actual, query["same_row_identity"])}
        queries.append(record)
        queries_by_id[query["id"]] = record
    return {
        "variant": variant,
        "retained_environment": environment,
        "batches": records,
        "queries": queries,
        "queries_by_id": queries_by_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--write-starter-spec",
        type=Path,
        help="write an incomplete tester-owned shell referencing the retained Cycle5 seed batches",
    )
    parser.add_argument(
        "--inspect-seed-items",
        nargs="+",
        metavar="SCENARIO_RELATIVE_BATCH",
        help="print a mechanical index/ref/type/payload inventory; does not select test roles or assertions",
    )
    parser.add_argument("--host", default="127.0.0.1:8012")
    parser.add_argument("--require-role-count", type=int, default=9)
    args = parser.parse_args()
    if args.inspect_seed_items:
        if args.spec or args.output or args.write_starter_spec:
            raise SystemExit("--inspect-seed-items cannot be combined with run or starter options")
        print(json.dumps(inspect_seed_items_files(args.inspect_seed_items), ensure_ascii=False, indent=2))
        return 0
    if args.write_starter_spec:
        if args.spec or args.output:
            raise SystemExit("--write-starter-spec cannot be combined with --spec or --output")
        args.write_starter_spec.write_text(
            json.dumps(starter_spec(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return 0
    if not args.spec or not args.output:
        raise SystemExit("--spec and --output are required unless writing a starter spec")
    spec = validate_spec(json.loads(args.spec.read_text(encoding="utf-8")), require_role_count=args.require_role_count)
    imported_seed_actions, seed_imports = load_seed_items_files(spec)
    spec = {**spec, "seed_actions": [*imported_seed_actions, *spec["seed_actions"]]}
    api = PublicApi(load_api_key(), args.host)
    variants = [
        run_variant(api, spec, variant="baseline", actions=[]),
        run_variant(api, spec, variant="decoy", actions=spec["orthogonal_decoy_actions"]),
    ]
    for role in spec["roles"]:
        for mutation in ("remove", "sentinel_replace"):
            variants.append(
                run_variant(
                    api,
                    spec,
                    variant=f"{role['id']}:{mutation}",
                    actions=[*spec["orthogonal_decoy_actions"], role[mutation]],
                )
            )
    # Evaluate each role mutation against the tester's same named mutation expectation.
    summaries = []
    baseline_and_decoy = variants[:2]
    for role in spec["roles"]:
        remove = next(variant for variant in variants[2:] if variant["variant"] == f"{role['id']}:remove")
        sentinel_replace = next(
            variant for variant in variants[2:] if variant["variant"] == f"{role['id']}:sentinel_replace"
        )
        summary = evaluate_queries(spec, baseline_and_decoy[0], baseline_and_decoy[1], remove, sentinel_replace)
        summary["role"] = role["id"]
        summaries.append(summary)
    result = {
        "spec_sha256": sha256_bytes(args.spec.read_bytes()),
        "seed_imports": seed_imports,
        "retention": "temporary acceptance Projects are retained; no direct RDF/database cleanup is performed",
        "variants": variants,
        "summary": {
            "passed": all(summary["passed"] for summary in summaries),
            "status": "PASS" if all(summary["passed"] for summary in summaries) else "FAIL",
            "evaluations": summaries,
        },
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if result["summary"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
