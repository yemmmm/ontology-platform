#!/usr/bin/env python3
"""Run a fresh, read-only M4 consumer through the same host-owned API spool boundary."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Final

import run_m4_clarification as modeling


SCENARIO_ROOT: Final = Path(__file__).resolve().parent
CONSUMER_PROMPT: Final = SCENARIO_ROOT / "consumer-input-pack" / "consumer-prompt.md"
CONSUMER_SLOTS: Final = ("current_target_contract", "output_continuity", "missing_score")
CONSUMER_RECORD_KEYS: Final = {
    "terminal_status",
    "scope",
    "receipts",
    "observations",
    "claim_classifications",
}
CLAIM_CLASSIFICATIONS: Final = {"source", "synthetic", "inference", "judgment"}
RECEIPT_KEYS: Final = {"request_id", "canonical_request_sha256", "response_sha256"}
CURRENT_TARGET_OBSERVATION_KEYS: Final = {"current_target", "target_version", "b_contract"}
OUTPUT_CONTINUITY_OBSERVATION_KEYS: Final = {
    "old_contract_change",
    "new_contract_change",
    "continuity",
}
MISSING_SCORE_OBSERVATION_KEYS: Final = {"state", "explicit_gap_observed", "gap"}


def _backend_get_json(api_key: str, backend_port: int, path: str) -> object:
    try:
        connection = http.client.HTTPConnection("127.0.0.1", backend_port, timeout=15)
        connection.request("GET", path, headers={"Authorization": f"Bearer {api_key}"})
        response = connection.getresponse()
        body = json.loads(response.read().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise modeling.IsolationError("consumer scope verification response is invalid") from error
    if response.status != 200:
        raise modeling.IsolationError("consumer scope verification request was not successful")
    return body


def verify_consumer_scope(
    api_key: str, backend_port: int, project_id: str, ontology_id: str, graph_set_id: str
) -> dict[str, str]:
    if not all(isinstance(value, str) and value for value in (project_id, ontology_id, graph_set_id)):
        raise modeling.IsolationError("consumer scope IDs must be non-empty strings")
    project = _backend_get_json(api_key, backend_port, f"/api/projects/{project_id}")
    ontology = _backend_get_json(api_key, backend_port, f"/api/ontologies/{ontology_id}")
    workspace = _backend_get_json(
        api_key, backend_port, f"/api/ontologies/{ontology_id}/workspace-context"
    )
    if (
        not isinstance(project, dict)
        or project.get("id") != project_id
        or not isinstance(ontology, dict)
        or ontology.get("id") != ontology_id
        or ontology.get("project_id") != project_id
        or not isinstance(workspace, dict)
        or workspace.get("ontology_id") != ontology_id
        or workspace.get("default_graph_set_id") != graph_set_id
    ):
        raise modeling.IsolationError("consumer Project/Ontology/graph-set scope does not match backend")
    return {"project_id": project_id, "ontology_id": ontology_id, "graph_set_id": graph_set_id}


def consumer_paths(run_root: Path, scope: dict[str, str]) -> dict[str, Path]:
    run_root.mkdir(mode=0o700, parents=True, exist_ok=False)
    paths = {
        "staging": run_root / "consumer-input",
        "workspace": run_root / "workspace",
        "clarification_responses": run_root / "host" / "empty-clarification-responses",
        "api_responses": run_root / "host" / "api-responses",
        "api_requests": run_root / "workspace" / "api" / "requests",
        "codex_home": run_root / "host" / "codex-home",
        "api_audit": run_root / "host" / "api-audit.jsonl",
        "transcript": run_root / "host" / "consumer-transcript.jsonl",
        "stderr": run_root / "host" / "consumer-stderr.log",
        "final_audit": run_root / "host" / "consumer-audit.json",
    }
    for path in (
        paths["staging"],
        paths["workspace"] / "api" / "requests",
        paths["workspace"] / "api" / "responses",
        paths["workspace"] / "clarifications" / "requests",
        paths["workspace"] / "clarifications" / "responses",
        paths["clarification_responses"],
        paths["api_responses"],
    ):
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    shutil.copyfile(CONSUMER_PROMPT, paths["staging"] / "consumer-prompt.md")
    os.chmod(paths["staging"] / "consumer-prompt.md", 0o444)
    (paths["staging"] / "consumer-scope.json").write_bytes(modeling.canonical_json(scope))
    os.chmod(paths["staging"] / "consumer-scope.json", 0o444)
    return paths


def validate_consumer_record(
    record_path: Path, api_audit_path: Path, scope: dict[str, str]
) -> tuple[dict[str, object] | None, list[str]]:
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
        audit_entries = [json.loads(line) for line in api_audit_path.read_text(encoding="utf-8").splitlines()]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None, ["consumer_record:missing_or_invalid"]
    if not isinstance(record, dict) or not all(isinstance(entry, dict) for entry in audit_entries):
        return None, ["consumer_record:missing_or_invalid"]
    errors: list[str] = []
    if set(record) != CONSUMER_RECORD_KEYS:
        errors.append("consumer_record:shape_invalid")
    if record.get("terminal_status") != "CONSUMER_READY":
        errors.append("consumer_record:not_ready")
    if record.get("scope") != scope:
        errors.append("consumer_record:scope_mismatch")
    receipts = record.get("receipts")
    if not isinstance(receipts, dict) or set(receipts) != set(CONSUMER_SLOTS):
        errors.append("consumer_record:receipt_slots_mismatch")
    else:
        for slot in CONSUMER_SLOTS:
            receipt = receipts[slot]
            if not isinstance(receipt, dict) or set(receipt) != RECEIPT_KEYS:
                errors.append(f"consumer_record:{slot}_receipt_invalid")
                continue
            bound = any(
                entry.get("policy") == "forwarded"
                and isinstance(entry.get("status"), int)
                and 200 <= entry["status"] < 300
                and entry.get("method") == "GET"
                and entry.get("path", "").startswith(
                    f"/api/ontologies/{scope['ontology_id']}/semantic-read-models/"
                )
                and receipt.get("request_id") == entry.get("request_id")
                and receipt.get("canonical_request_sha256") == entry.get("canonical_request_sha256")
                and receipt.get("response_sha256") == entry.get("response_sha256")
                for entry in audit_entries
            )
            if not bound:
                errors.append(f"consumer_record:{slot}_receipt_unbound")
    observations = record.get("observations")
    if not isinstance(observations, dict) or set(observations) != set(CONSUMER_SLOTS):
        errors.append("consumer_record:observation_slots_mismatch")
    else:
        current_target = observations["current_target_contract"]
        if (
            not isinstance(current_target, dict)
            or set(current_target) != CURRENT_TARGET_OBSERVATION_KEYS
            or any(
                not isinstance(current_target.get(key), str) or not current_target[key].strip()
                for key in CURRENT_TARGET_OBSERVATION_KEYS
            )
        ):
            errors.append("consumer_record:current_target_contract_observation_invalid")
        continuity = observations["output_continuity"]
        if (
            not isinstance(continuity, dict)
            or set(continuity) != OUTPUT_CONTINUITY_OBSERVATION_KEYS
            or any(
                not isinstance(continuity.get(key), str) or not continuity[key].strip()
                for key in OUTPUT_CONTINUITY_OBSERVATION_KEYS
            )
        ):
            errors.append("consumer_record:output_continuity_observation_invalid")
        missing_score = observations["missing_score"]
        if (
            not isinstance(missing_score, dict)
            or set(missing_score) != MISSING_SCORE_OBSERVATION_KEYS
            or missing_score.get("state") != "unknown"
            or missing_score.get("explicit_gap_observed") is not True
            or not isinstance(missing_score.get("gap"), str)
            or not missing_score["gap"].strip()
        ):
            errors.append("consumer_record:missing_score_observation_invalid")
    classifications = record.get("claim_classifications")
    if (
        not isinstance(classifications, dict)
        or set(classifications) != set(CONSUMER_SLOTS)
        or any(value not in CLAIM_CLASSIFICATIONS for value in classifications.values())
    ):
        errors.append("consumer_record:claim_classifications_invalid")
    return record, errors


def consumer_final_status(
    agent_exit_code: int, record: dict[str, object] | None, validation_errors: list[str]
) -> str:
    if agent_exit_code == 0 and not validation_errors:
        return "COMPLETED"
    if isinstance(record, dict) and record.get("terminal_status") == "BLOCKED":
        return "BLOCKED"
    return "INCONCLUSIVE"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--run-tag", default="m4-readonly-consumer")
    parser.add_argument("--backend-port", type=int, default=8012)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--ontology-id", required=True)
    parser.add_argument("--graph-set-id", required=True)
    args = parser.parse_args()
    api_key = modeling.load_api_key()
    canonical_mode = modeling.verify_isolated_write_mode(api_key, args.backend_port)
    scope = verify_consumer_scope(
        api_key, args.backend_port, args.project_id, args.ontology_id, args.graph_set_id
    )
    paths = consumer_paths(args.run_root, scope)
    modeling.prepare_codex_home(paths)
    environment = {**os.environ, "M4_HOST_API_KEY": api_key}
    command = modeling.api_gateway_command(
        paths, args.backend_port, watch=True, read_only_scope=scope
    )
    gateway = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=environment)
    exit_code = 125
    try:
        with paths["transcript"].open("wb") as transcript, paths["stderr"].open("wb") as stderr:
            result = subprocess.run(
                modeling.agent_command(paths, args.run_tag),
                input=(paths["staging"] / "consumer-prompt.md").read_bytes(),
                stdout=transcript,
                stderr=stderr,
                timeout=args.timeout_seconds,
                check=False,
            )
            exit_code = result.returncode
    except subprocess.TimeoutExpired:
        exit_code = 124
    finally:
        modeling._terminate(gateway)
    record = paths["workspace"] / "consumer-record.json"
    record_value, validation_errors = validate_consumer_record(record, paths["api_audit"], scope)
    status = consumer_final_status(exit_code, record_value, validation_errors)
    audit = {
        "run_tag": args.run_tag,
        "agent_exit_code": exit_code,
        "canonical_mode": canonical_mode,
        "scope": scope,
        "consumer_record_sha256": modeling.sha256(record) if record.is_file() else None,
        "api_audit_sha256": modeling.sha256(paths["api_audit"]) if paths["api_audit"].is_file() else None,
        "validation_errors": validation_errors,
        "status": status,
    }
    paths["final_audit"].write_bytes(modeling.canonical_json(audit))
    print(json.dumps({"run_root": str(args.run_root), **audit}, sort_keys=True))
    return 0 if audit["status"] == "COMPLETED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
