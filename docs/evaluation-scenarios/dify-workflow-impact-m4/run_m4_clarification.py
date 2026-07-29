#!/usr/bin/env python3
"""Prepare an auditable, isolated M4 Agent namespace and host clarification service."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import hashlib
import http.client
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Final

from m4_clarification_responder import (
    PolicyError,
    canonical_json,
    decision_fingerprint,
    hidden_contract_json,
    load_hidden_contract,
    sha256_bytes,
)


SCENARIO_ROOT: Final = Path(__file__).resolve().parent
REPOSITORY_ROOT: Final = SCENARIO_ROOT.parents[2]
MANIFEST_PATH: Final = SCENARIO_ROOT / "input-pack" / "input-manifest.json"
FROZEN_MANIFEST_SHA256: Final = "0338d2075068bb11d3716895cbce3eb1ac6174142022854a4e2ab2344f0d8d19"
RUN_TAG_RE: Final = re.compile(r"^[a-z0-9][a-z0-9-]{2,80}$")
CODEX_BINARY: Final = Path("/home/yangxiang/.local/bin/codex")
HOST_CODEX_AUTH: Final = Path("/home/yangxiang/.codex/auth.json")
PROXY_ENV_PAIRS: Final = (("HTTPS_PROXY", "https_proxy"), ("HTTP_PROXY", "http_proxy"))
SUCCESS_RECEIPTS: Final = (
    "principal_schema_dry_run",
    "shape_apply",
    "valid_instance_dry_run",
    "validation",
    "reasoning",
    "governed_query",
    "pre_checkpoint_get",
    "checkpoint",
    "complete",
    "final_get",
)
REJECTION_RECEIPT: Final = "invalid_shape_dry_run"
FIRST_INSTANCE_APPLY_RECEIPT: Final = "valid_instance_apply"
CORRECTION_DRY_RECEIPT: Final = "correction_instance_dry_run"
CORRECTION_APPLY_RECEIPT: Final = "correction_instance_apply"
RECEIPT_ORDER: Final = (*SUCCESS_RECEIPTS[:4], FIRST_INSTANCE_APPLY_RECEIPT, *SUCCESS_RECEIPTS[4:], REJECTION_RECEIPT)
SCHEMA_COMMAND_KINDS: Final = frozenset(
    {"create_class", "create_property", "create_relation_type", "create_shape"}
)
INSTANCE_COMMAND_KINDS: Final = frozenset({"create_entity", "create_relation"})


class IsolationError(RuntimeError):
    """Raised when a run would expose inputs outside the M4 contract."""


def allowed_proxy_environment(environ: dict[str, str] | None = None) -> dict[str, str]:
    """Forward only HTTPS/HTTP proxy endpoints, with both spellings for client compatibility."""
    source = os.environ if environ is None else environ
    selected: dict[str, str] = {}
    for uppercase, lowercase in PROXY_ENV_PAIRS:
        value = source.get(uppercase) or source.get(lowercase)
        if value:
            selected[uppercase] = value
            selected[lowercase] = value
    return selected


def proxy_audit(proxy_environment: dict[str, str]) -> list[dict[str, str]]:
    """Record only names and hashes; proxy endpoints are not written into host audits."""
    return [
        {"name": name, "value_sha256": sha256_bytes(value.encode("utf-8"))}
        for name, value in sorted(proxy_environment.items())
    ]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative_path(value: str, label: str) -> Path:
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise IsolationError(f"unsafe {label}: {value!r}")
    return path


def read_manifest() -> dict[str, Any]:
    if sha256(MANIFEST_PATH) != FROZEN_MANIFEST_SHA256:
        raise IsolationError("frozen M4 manifest SHA-256 mismatch")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("mount_policy") != "copy each listed file to its mounted_path; never mount a source directory":
        raise IsolationError("unexpected M4 mount policy")
    return manifest


def verify_and_stage(manifest: dict[str, Any], staging: Path) -> dict[str, object]:
    staging.mkdir(mode=0o700, parents=True, exist_ok=False)
    shutil.copyfile(MANIFEST_PATH, staging / "input-manifest.json")
    os.chmod(staging / "input-manifest.json", 0o444)
    declared = {"input-manifest.json"}
    hashes: list[dict[str, str]] = []
    for item in manifest["files"]:
        source_path = relative_path(item["source_path"], "source_path")
        mounted_path = relative_path(item["mounted_path"], "mounted_path")
        if mounted_path.as_posix() in declared:
            raise IsolationError("duplicate staged mount path")
        source = (REPOSITORY_ROOT / source_path).resolve()
        if REPOSITORY_ROOT not in source.parents or sha256(source) != item["sha256"]:
            raise IsolationError(f"source hash mismatch for {source_path}")
        target = staging / mounted_path
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        os.chmod(target, 0o444)
        declared.add(mounted_path.as_posix())
        hashes.append({"mounted_path": mounted_path.as_posix(), "sha256": item["sha256"]})
    actual = {path.relative_to(staging).as_posix() for path in staging.rglob("*") if path.is_file()}
    if actual != declared:
        raise IsolationError("staged file set differs from frozen manifest")
    return {"declared_mount_set": sorted(declared), "file_hashes": hashes}


def prepare_layout(run_root: Path, variant: str, run_tag: str) -> dict[str, Path]:
    if not RUN_TAG_RE.fullmatch(run_tag):
        raise IsolationError("run tag is unsafe")
    run_root.mkdir(mode=0o700, parents=True, exist_ok=False)
    paths = {
        "staging": run_root / "agent-input",
        "workspace": run_root / "workspace",
        "clarification_requests": run_root / "workspace" / "clarifications" / "requests",
        "clarification_response_mount": run_root / "workspace" / "clarifications" / "responses",
        "clarification_responses": run_root / "host" / "clarification-responses",
        "api_requests": run_root / "workspace" / "api" / "requests",
        "api_response_mount": run_root / "workspace" / "api" / "responses",
        "api_responses": run_root / "host" / "api-responses",
        "api_audit": run_root / "host" / "api-gateway-audit.jsonl",
        "host_contract": run_root / "host" / "hidden-contract.json",
        "host_audit": run_root / "host" / "clarification-audit.jsonl",
        "mount_audit": run_root / "host" / "mount-audit.json",
        "codex_home": run_root / "host" / "codex-home",
        "transcript": run_root / "host" / "agent-transcript.jsonl",
        "stderr": run_root / "host" / "agent-stderr.log",
        "run_audit": run_root / "host" / "final-run-audit.json",
    }
    for name in (
        "workspace",
        "clarification_requests",
        "clarification_response_mount",
        "clarification_responses",
        "api_requests",
        "api_response_mount",
        "api_responses",
    ):
        paths[name].mkdir(mode=0o700, parents=True, exist_ok=True)
    contract = hidden_contract_json(variant)
    paths["host_contract"].parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    paths["host_contract"].write_bytes(contract)
    os.chmod(paths["host_contract"], 0o400)
    return paths


def responder_command(paths: dict[str, Path], *, watch: bool = False) -> list[str]:
    command = [
        sys.executable,
        str(SCENARIO_ROOT / "m4_clarification_responder.py"),
        "--requests",
        str(paths["clarification_requests"]),
        "--responses",
        str(paths["clarification_responses"]),
        "--audit",
        str(paths["host_audit"]),
        "--contract",
        str(paths["host_contract"]),
    ]
    if watch:
        command.append("--watch")
    return command


def api_gateway_command(
    paths: dict[str, Path],
    backend_port: int,
    *,
    watch: bool = False,
    read_only_scope: dict[str, str] | None = None,
) -> list[str]:
    command = [
        sys.executable,
        str(SCENARIO_ROOT / "m4_api_file_spool_gateway.py"),
        "--requests",
        str(paths["api_requests"]),
        "--responses",
        str(paths["api_responses"]),
        "--audit",
        str(paths["api_audit"]),
        "--api-key-env",
        "M4_HOST_API_KEY",
        "--backend-port",
        str(backend_port),
    ]
    if read_only_scope is not None:
        command.extend(
            [
                "--read-only",
                "--consumer-project-id",
                read_only_scope["project_id"],
                "--consumer-ontology-id",
                read_only_scope["ontology_id"],
                "--consumer-graph-set-id",
                read_only_scope["graph_set_id"],
            ]
        )
    if watch:
        command.append("--watch")
    return command


def bwrap_command(paths: dict[str, Path], run_tag: str, codex_binary: Path) -> list[str]:
    """Build the Agent command without ever adding the host contract or audit as a mount."""
    command = ["bwrap", "--die-with-parent", "--new-session", "--share-net", "--clearenv"]
    for source in ("/usr", "/bin", "/lib", "/lib64", "/etc/ssl", "/etc/hosts", "/etc/resolv.conf"):
        if Path(source).exists():
            command.extend(["--ro-bind", source, source])
    command.extend(
        [
            "--ro-bind",
            str(codex_binary.resolve()),
            "/codex",
            "--ro-bind",
            str(paths["staging"]),
            "/opt",
            "--bind",
            str(paths["workspace"]),
            "/mnt",
            "--bind",
            str(paths["codex_home"]),
            "/codex-home",
            "--ro-bind",
            str(paths["clarification_responses"]),
            "/mnt/clarifications/responses",
            "--ro-bind",
            str(paths["api_responses"]),
            "/mnt/api/responses",
            "--setenv",
            "M4_CLARIFICATION_REQUEST_DIR",
            "/mnt/clarifications/requests",
            "--setenv",
            "M4_CLARIFICATION_RESPONSE_DIR",
            "/mnt/clarifications/responses",
            "--setenv",
            "M4_API_REQUEST_DIR",
            "/mnt/api/requests",
            "--setenv",
            "M4_API_RESPONSE_DIR",
            "/mnt/api/responses",
            "--setenv",
            "M4_RUN_TAG",
            run_tag,
            "--setenv",
            "CODEX_HOME",
            "/codex-home",
            "--setenv",
            "HOME",
            "/tmp",
            "--setenv",
            "PATH",
            "/usr/bin:/bin",
            "--dev",
            "/dev",
            "--proc",
            "/proc",
            "--tmpfs",
            "/tmp",
        ]
    )
    for name, value in allowed_proxy_environment().items():
        command.extend(["--setenv", name, value])
    return command


def load_api_key() -> str:
    environment = REPOSITORY_ROOT / "backend" / ".env"
    if not environment.is_file():
        raise IsolationError("backend/.env is required for the host API gateway")
    for line in environment.read_text(encoding="utf-8").splitlines():
        if line.startswith("ONTOLOGY_MCP_API_KEY="):
            value = line.partition("=")[2].strip().strip("\"'")
            if value:
                return value
    raise IsolationError("backend/.env has no ONTOLOGY_MCP_API_KEY")


def verify_isolated_write_mode(api_key: str, backend_port: int) -> dict[str, object]:
    try:
        connection = http.client.HTTPConnection("127.0.0.1", backend_port, timeout=15)
        connection.request("GET", "/api/semantic/canonical-mode", headers={"Authorization": f"Bearer {api_key}"})
        response = connection.getresponse()
        body = json.loads(response.read().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IsolationError("isolated backend canonical-mode response is invalid") from error
    if response.status != 200 or body.get("product_write_mode") != "rdf_primary":
        raise IsolationError("formal M4 run requires an isolated rdf_primary backend")
    return body


def prepare_codex_home(paths: dict[str, Path]) -> None:
    if not CODEX_BINARY.is_file() or not HOST_CODEX_AUTH.is_file():
        raise IsolationError("Codex executable or host authentication is unavailable")
    paths["codex_home"].mkdir(mode=0o700, parents=True, exist_ok=False)
    shutil.copyfile(HOST_CODEX_AUTH, paths["codex_home"] / "auth.json")
    os.chmod(paths["codex_home"] / "auth.json", 0o600)


def agent_command(paths: dict[str, Path], run_tag: str) -> list[str]:
    return bwrap_command(paths, run_tag, CODEX_BINARY) + [
        "--",
        "/codex",
        "exec",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write",
        "--disable",
        "apps",
        "--disable",
        "browser_use",
        "--disable",
        "plugins",
        "--disable",
        "memories",
        "-C",
        "/mnt",
        "-",
    ]


def write_mount_audit(paths: dict[str, Path], stage: dict[str, object], run_tag: str) -> dict[str, object]:
    agent_visible = [paths["staging"], paths["workspace"], paths["clarification_responses"], paths["api_responses"]]
    host_only = [paths["host_contract"], paths["host_audit"], paths["mount_audit"]]
    if any(host_path in agent_visible for host_path in host_only):
        raise IsolationError("a host-only M4 artifact would be Agent-visible")
    record = {
        "run_tag": run_tag,
        "staged": stage,
        "agent_visible_mounts": [str(path) for path in agent_visible],
        "host_only_paths": [str(path) for path in host_only],
        "host_contract_sha256": sha256(paths["host_contract"]),
        "clarification_response_mode": oct(stat.S_IMODE(os.stat(paths["clarification_responses"]).st_mode)),
        "proxy_environment": proxy_audit(allowed_proxy_environment()),
    }
    paths["mount_audit"].write_bytes(canonical_json(record))
    os.chmod(paths["mount_audit"], 0o400)
    return record


def prepare_run(run_root: Path, variant: str, run_tag: str) -> dict[str, object]:
    manifest = read_manifest()
    paths = prepare_layout(run_root, variant, run_tag)
    stage = verify_and_stage(manifest, paths["staging"])
    audit = write_mount_audit(paths, stage, run_tag)
    return {
        "status": "PREPARED",
        "run_tag": run_tag,
        "mount_audit": audit,
        "responder_command": responder_command(paths),
        "host_contract_sha256": sha256_bytes(paths["host_contract"].read_bytes()),
    }


def _prepare_execution(run_root: Path, variant: str, run_tag: str) -> tuple[dict[str, Path], dict[str, object]]:
    manifest = read_manifest()
    paths = prepare_layout(run_root, variant, run_tag)
    stage = verify_and_stage(manifest, paths["staging"])
    return paths, write_mount_audit(paths, stage, run_tag)


def _terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def _response_inventory(directory: Path) -> list[dict[str, str]]:
    inventory: list[dict[str, str]] = []
    for path in sorted(directory.glob("*.json")):
        inventory.append({"filename": path.name, "sha256": sha256(path)})
    return inventory


def _clarification_timeline_errors(
    paths: dict[str, Path], events: list[dict[str, object]], run_tag: str
) -> list[str]:
    """Require all visible-brief gaps from host receipts before the principal schema request."""
    principal = next(
        (
            event
            for event in events
            if event.get("request_id")
            and isinstance(event.get("request_summary"), dict)
            and _is_principal_schema_batch(event["request_summary"], "dry_run")
        ),
        None,
    )
    principal_time = _event_time(principal) if isinstance(principal, dict) else None
    if principal_time is None:
        return ["clarification:missing_principal_schema_observation"]
    try:
        audit_entries = [json.loads(line) for line in paths["host_audit"].read_text(encoding="utf-8").splitlines()]
        consumption_lines = (paths["workspace"] / "clarification-consumption-receipts.jsonl").read_bytes().splitlines()
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return ["clarification:missing_or_invalid_host_evidence"]
    if not all(isinstance(entry, dict) for entry in audit_entries):
        return ["clarification:missing_or_invalid_host_evidence"]
    responded = [entry for entry in audit_entries if entry.get("policy") == "responded"]
    try:
        expected = {
            decision_fingerprint(decision): "answered" if decision.answer is not None else "uncertain"
            for decision in load_hidden_contract(paths["host_contract"])
        }
    except (OSError, PolicyError):
        return ["clarification:missing_or_invalid_host_evidence"]
    eligible = [
        entry
        for entry in responded
        if isinstance(entry.get("decision_fingerprint"), str)
        and entry.get("status") == expected.get(entry["decision_fingerprint"])
    ]
    errors: list[str] = []
    fingerprints = [entry.get("decision_fingerprint") for entry in eligible]
    if len(eligible) != len(expected) or set(fingerprints) != set(expected):
        errors.append("clarification:missing_or_duplicate_visible_gap")
    previous_time: datetime | None = None
    consumption: dict[str, dict[str, object]] = {}
    for raw in consumption_lines:
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            errors.append("clarification:invalid_consumption_receipt")
            continue
        if not isinstance(value, dict) or canonical_json(value) != raw:
            errors.append("clarification:invalid_consumption_receipt")
            continue
        request_id = value.get("request_id")
        if not isinstance(request_id, str) or request_id in consumption:
            errors.append("clarification:invalid_consumption_receipt")
            continue
        consumption[request_id] = value
    for entry in eligible:
        request_id = entry.get("request_id")
        response_sha256 = entry.get("response_sha256")
        fingerprint = entry.get("decision_fingerprint")
        event_time = _event_time(entry)
        if (
            not isinstance(request_id, str)
            or not isinstance(response_sha256, str)
            or not isinstance(fingerprint, str)
            or entry.get("status") != expected.get(fingerprint)
            or event_time is None
            or event_time >= principal_time
            or (previous_time is not None and event_time <= previous_time)
        ):
            errors.append("clarification:host_observed_order_or_status_invalid")
            continue
        previous_time = event_time
        request_path = paths["clarification_requests"] / f"{request_id}.json"
        response_path = paths["clarification_responses"] / f"{request_id}.json"
        receipt = consumption.get(request_id)
        if (
            not request_path.is_file()
            or not response_path.is_file()
            or sha256(request_path) != entry.get("raw_request_sha256")
            or sha256(response_path) != response_sha256
            or not isinstance(receipt, dict)
            or receipt.get("run_tag") != run_tag
            or receipt.get("response_id") != request_id
            or receipt.get("response_sha256") != response_sha256
            or receipt.get("status") != entry.get("status")
            or receipt.get("response_read_confirmed") is not True
        ):
            errors.append("clarification:hash_bound_consumption_missing")
    return errors


def _load_json_object(path: Path) -> tuple[dict[str, object] | None, str | None]:
    if not path.is_file():
        return None, "missing"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None, "invalid_json"
    return (value, None) if isinstance(value, dict) else (None, "not_an_object")


def _forwarded_api_receipts(
    path: Path,
) -> tuple[list[dict[str, object]], dict[str, dict[str, object]], str | None]:
    if not path.is_file():
        return [], {}, "missing"
    receipts: dict[str, dict[str, object]] = {}
    events: list[dict[str, object]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            value = json.loads(line)
            if not isinstance(value, dict):
                return {}, "invalid_jsonl"
            request_id = value.get("request_id")
            if value.get("policy") == "forwarded" and isinstance(request_id, str):
                receipts[request_id] = value
                events.append(value)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return [], {}, "invalid_jsonl"
    return events, receipts, None


def _receipt_matches_audit(
    receipt: object, forwarded: dict[str, dict[str, object]], *, success: bool
) -> str | None:
    if not isinstance(receipt, dict):
        return "missing_or_invalid_receipt"
    request_id, status, response_sha256 = (
        receipt.get("request_id"),
        receipt.get("status"),
        receipt.get("raw_response_sha256"),
    )
    if not isinstance(request_id, str) or not request_id:
        return "missing_request_id"
    if not isinstance(status, int) or (not 200 <= status < 300 if success else not 400 <= status < 600):
        return "unexpected_receipt_status"
    if not isinstance(response_sha256, str) or len(response_sha256) != 64:
        return "missing_response_hash"
    canonical_request_sha256 = receipt.get("canonical_request_sha256")
    if not isinstance(canonical_request_sha256, str) or len(canonical_request_sha256) != 64:
        return "missing_canonical_request_hash"
    observed = forwarded.get(request_id)
    if observed is None:
        return "request_not_forwarded"
    if (
        observed.get("status") != status
        or observed.get("response_sha256") != response_sha256
        or observed.get("canonical_request_sha256") != canonical_request_sha256
    ):
        return "gateway_receipt_mismatch"
    return None


def _gateway_response_body(
    paths: dict[str, Path], receipt: object, forwarded: dict[str, dict[str, object]]
) -> tuple[dict[str, object] | None, dict[str, object] | None, str | None]:
    if not isinstance(receipt, dict):
        return None, None, "missing_or_invalid_receipt"
    request_id = receipt.get("request_id")
    if not isinstance(request_id, str):
        return None, None, "missing_request_id"
    audit = forwarded.get(request_id)
    if audit is None:
        return None, None, "request_not_forwarded"
    filename = audit.get("response_filename", f"{request_id}.json")
    if filename != f"{request_id}.json":
        return None, None, "unsafe_response_filename"
    response_path = paths["api_responses"] / filename
    if not response_path.is_file() or response_path.is_symlink():
        return None, None, "missing_host_response"
    raw = response_path.read_bytes()
    if sha256_bytes(raw) != audit.get("response_sha256"):
        return None, None, "host_response_hash_mismatch"
    try:
        envelope = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, None, "invalid_host_response"
    if not isinstance(envelope, dict) or set(envelope) != {"id", "status", "headers", "body"}:
        return None, None, "invalid_host_response_envelope"
    if envelope.get("id") != request_id or envelope.get("status") != receipt.get("status"):
        return None, None, "host_response_receipt_mismatch"
    body = envelope.get("body")
    return (body if isinstance(body, dict) else None), audit, None


def _positive_query_result(result: object) -> bool:
    if result is True:
        return True
    if isinstance(result, dict):
        bindings = result.get("results")
        if isinstance(bindings, dict) and isinstance(bindings.get("bindings"), list):
            return bool(bindings["bindings"])
    return False


def _endpoint_session_id(name: str, audit: dict[str, object]) -> tuple[str | None, str | None]:
    path, method = audit.get("path"), audit.get("method")
    patterns = {
        "principal_schema_dry_run": ("POST", r"/api/build-sessions/([^/]+)/modeling-batches"),
        "shape_apply": ("POST", r"/api/build-sessions/([^/]+)/modeling-batches"),
        "invalid_shape_dry_run": ("POST", r"/api/build-sessions/([^/]+)/modeling-batches"),
        "valid_instance_dry_run": ("POST", r"/api/build-sessions/([^/]+)/modeling-batches"),
        "valid_instance_apply": ("POST", r"/api/build-sessions/([^/]+)/modeling-batches"),
        "correction_instance_dry_run": ("POST", r"/api/build-sessions/([^/]+)/modeling-batches"),
        "correction_instance_apply": ("POST", r"/api/build-sessions/([^/]+)/modeling-batches"),
        "validation": ("POST", r"/api/semantic/validation-runs"),
        "reasoning": ("POST", r"/api/semantic/graph-sets/([^/]+)/reasoning-runs"),
        "governed_query": ("POST", r"/api/semantic/sparql:query"),
        "pre_checkpoint_get": ("GET", r"/api/build-sessions/([^/]+)"),
        "checkpoint": ("POST", r"/api/build-sessions/([^/]+)/checkpoints"),
        "complete": ("POST", r"/api/build-sessions/([^/]+):complete"),
        "final_get": ("GET", r"/api/build-sessions/([^/]+)"),
    }
    expected_method, pattern = patterns[name]
    match = re.fullmatch(pattern, path) if isinstance(path, str) and method == expected_method else None
    return (match.group(1) if match and match.lastindex else None, None if match else "unexpected_endpoint")


def _event_time(event: dict[str, object]) -> datetime | None:
    value = event.get("at")
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else None


def _command_kinds(summary: object) -> list[str] | None:
    if not isinstance(summary, dict):
        return None
    kinds = summary.get("command_kinds")
    return kinds if isinstance(kinds, list) and all(isinstance(kind, str) for kind in kinds) else None


def _is_principal_schema_batch(summary: object, mode: str) -> bool:
    kinds = _command_kinds(summary)
    return (
        kinds is not None
        and bool(kinds)
        and "create_shape" in kinds
        and bool(set(kinds).intersection(SCHEMA_COMMAND_KINDS))
        and isinstance(summary, dict)
        and summary.get("contains_create_shape") is True
        and summary.get("mode") == mode
    )


def _is_instance_batch(summary: object, mode: str) -> bool:
    kinds = _command_kinds(summary)
    return (
        kinds is not None
        and bool(kinds)
        and set(kinds).issubset(INSTANCE_COMMAND_KINDS)
        and isinstance(summary, dict)
        and summary.get("contains_create_shape") is False
        and summary.get("mode") == mode
    )


def _is_pre_principal_probe(event: dict[str, object]) -> bool:
    """Allow setup/context reads, but never a model or semantic probe before the schema anchor."""
    path = event.get("path")
    if not isinstance(path, str):
        return False
    return (
        path.endswith("/modeling-batches")
        or path.startswith("/api/semantic/")
        or "/schema" in path
        or "/operation" in path
        or "/rule" in path
        or ":query" in path
    )


def _qualifying_instance_failure(body: object) -> bool:
    if not isinstance(body, dict) or body.get("mode") != "dry_run":
        return False
    if body.get("attempt_status") != "validation_failed" or body.get("batch_status") == "applied":
        return False
    findings = body.get("findings")
    blocking = [finding for finding in findings if isinstance(finding, dict) and finding.get("blocking") is True] if isinstance(findings, list) else []
    return bool(blocking) and all(
        finding.get("code") == "shacl_violation"
        and isinstance(finding.get("finding_fingerprint"), str)
        and bool(finding["finding_fingerprint"])
        and isinstance(finding.get("client_item_ids"), list)
        and bool(finding["client_item_ids"])
        and all(isinstance(item_id, str) and item_id for item_id in finding["client_item_ids"])
        for finding in blocking
    ) and len(blocking) == sum(
        1 for finding in findings if isinstance(finding, dict) and finding.get("blocking") is True
    )


def _modeling_target_errors(
    principal_schema_dry_run: object,
    shape_apply: object,
    intentional_invalid: object,
    first_candidate: object,
    *candidate_tail: object,
) -> list[str]:
    """Verify graph-set and pre/post-schema continuity without conflating phases."""
    named_bodies = {
        "principal_schema_dry_run": principal_schema_dry_run,
        "shape_apply": shape_apply,
        "invalid_shape_dry_run": intentional_invalid,
        "valid_instance_dry_run": first_candidate,
        **{f"candidate_tail_{index}": body for index, body in enumerate(candidate_tail)},
    }
    targets: dict[str, dict[str, object]] = {}
    errors: list[str] = []
    for name, body in named_bodies.items():
        target = body.get("target") if isinstance(body, dict) else None
        if (
            not isinstance(target, dict)
            or not isinstance(target.get("graph_set_id"), str)
            or not target["graph_set_id"]
            or not isinstance(target.get("source_signature_before"), str)
            or not target["source_signature_before"]
        ):
            errors.append("modeling_target:missing_target_evidence")
            continue
        targets[name] = target
    if len(targets) != len(named_bodies):
        return errors
    if len({target["graph_set_id"] for target in targets.values()}) != 1:
        errors.append("modeling_target:graph_set_id_mismatch")
    if (
        targets["principal_schema_dry_run"]["source_signature_before"]
        != targets["shape_apply"]["source_signature_before"]
    ):
        errors.append("modeling_target:schema_before_mismatch")
    schema_after = targets["shape_apply"].get("source_signature_after")
    if not isinstance(schema_after, str) or not schema_after:
        errors.append("modeling_target:missing_schema_after")
    elif any(
        targets[name]["source_signature_before"] != schema_after
        for name in ("invalid_shape_dry_run", "valid_instance_dry_run")
    ):
        errors.append("modeling_target:post_schema_signature_mismatch")
    if candidate_tail and len(
        {
            targets[name]["source_signature_before"]
            for name in ("valid_instance_dry_run", *[f"candidate_tail_{index}" for index in range(len(candidate_tail))])
        }
    ) != 1:
        errors.append("modeling_target:instance_signature_mismatch")
    return errors


def _item_summary_map(summary: object) -> dict[str, dict[str, object]] | None:
    if not isinstance(summary, dict) or not isinstance(summary.get("item_summaries"), list):
        return None
    result: dict[str, dict[str, object]] = {}
    for item in summary["item_summaries"]:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("client_item_id"), str)
            or not item["client_item_id"]
            or not isinstance(item.get("command_kind"), str)
            or not isinstance(item.get("depends_on"), list)
            or not isinstance(item.get("canonical_item_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", item["canonical_item_sha256"])
            or item["client_item_id"] in result
        ):
            return None
        result[item["client_item_id"]] = item
    return result


def _correction_evidence_errors(
    paths: dict[str, Path],
    runtime: dict[str, object],
    receipts: dict[str, object],
    valid_dry: dict[str, object],
    valid_dry_summary: object,
    correction_dry_summary: object,
    correction_apply_summary: object,
) -> list[str]:
    """Verify the one correction branch without retaining Agent request bodies in host audit."""
    errors: list[str] = []
    original_items = _item_summary_map(valid_dry_summary)
    correction_items = _item_summary_map(correction_dry_summary)
    apply_items = _item_summary_map(correction_apply_summary)
    if original_items is None or correction_items is None or apply_items is None:
        return ["correction_instance:missing_item_summary"]
    if set(original_items) != set(correction_items):
        errors.append("correction_instance:item_id_set_changed")
    if set(correction_items) != set(apply_items):
        errors.append("correction_instance:apply_item_id_set_changed")
    if correction_items != apply_items:
        errors.append("correction_instance:apply_items_changed")
    if not errors:
        for item_id, original in original_items.items():
            correction = correction_items[item_id]
            if original["command_kind"] != correction["command_kind"]:
                errors.append("correction_instance:command_kind_changed")
                break
            if original["depends_on"] != correction["depends_on"]:
                errors.append("correction_instance:depends_on_changed")
                break
    changed_item_ids = (
        [
            item_id
            for item_id, original in original_items.items()
            if item_id in correction_items
            and original["canonical_item_sha256"] != correction_items[item_id]["canonical_item_sha256"]
        ]
        if not errors
        else []
    )
    if not changed_item_ids:
        errors.append("correction_instance:no_changed_item")
    findings = valid_dry.get("findings")
    finding_item_ids: dict[str, set[str]] = {}
    if isinstance(findings, list):
        for finding in findings:
            if isinstance(finding, dict) and finding.get("blocking") is True:
                fingerprint = finding.get("finding_fingerprint")
                item_ids = finding.get("client_item_ids")
                if isinstance(fingerprint, str) and isinstance(item_ids, list):
                    finding_item_ids[fingerprint] = {
                        item_id for item_id in item_ids if isinstance(item_id, str) and item_id
                    }
    allowed_item_ids = set().union(*finding_item_ids.values()) if finding_item_ids else set()
    if not set(changed_item_ids).issubset(allowed_item_ids):
        errors.append("correction_instance:changed_item_not_in_finding")

    evidence = runtime.get("instance_correction")
    if not isinstance(evidence, dict):
        return [*errors, "correction_instance:missing_evidence"]
    original_receipt = receipts.get("valid_instance_dry_run")
    correction_receipt = receipts.get(CORRECTION_DRY_RECEIPT)
    if not isinstance(original_receipt, dict) or not isinstance(correction_receipt, dict):
        return [*errors, "correction_instance:missing_evidence"]
    expected_fingerprints = sorted(finding_item_ids)
    if (
        evidence.get("original_request_id") != original_receipt.get("request_id")
        or evidence.get("original_request_sha256") != original_receipt.get("canonical_request_sha256")
        or evidence.get("original_response_sha256") != original_receipt.get("raw_response_sha256")
        or evidence.get("original_batch_id") != valid_dry_summary.get("client_batch_id")
        or evidence.get("correction_dry_run_request_id") != correction_receipt.get("request_id")
        or evidence.get("correction_dry_run_request_sha256") != correction_receipt.get("canonical_request_sha256")
        or evidence.get("correction_dry_run_response_sha256") != correction_receipt.get("raw_response_sha256")
        or evidence.get("correction_batch_id") != correction_dry_summary.get("client_batch_id")
        or evidence.get("original_finding_fingerprints") != expected_fingerprints
    ):
        errors.append("correction_instance:evidence_binding_mismatch")
    changed_evidence = evidence.get("changed_items")
    if not isinstance(changed_evidence, list) or len(changed_evidence) != len(changed_item_ids):
        errors.append("correction_instance:changed_item_evidence_mismatch")
    else:
        evidence_by_id: dict[str, dict[str, object]] = {}
        for item in changed_evidence:
            if not isinstance(item, dict) or not isinstance(item.get("client_item_id"), str):
                continue
            evidence_by_id[item["client_item_id"]] = item
        if set(evidence_by_id) != set(changed_item_ids):
            errors.append("correction_instance:changed_item_evidence_mismatch")
        else:
            for item_id in changed_item_ids:
                item = evidence_by_id[item_id]
                if (
                    item.get("before_sha256") != original_items[item_id]["canonical_item_sha256"]
                    or item.get("after_sha256") != correction_items[item_id]["canonical_item_sha256"]
                    or item.get("reason_finding_fingerprint") not in finding_item_ids
                    or item_id not in finding_item_ids[item["reason_finding_fingerprint"]]
                ):
                    errors.append("correction_instance:changed_item_evidence_mismatch")
                    break
    expected_log = canonical_json({"event": "instance_correction", "evidence": evidence})
    try:
        correction_lines = [
            line
            for line in (paths["workspace"] / "decision-log.jsonl").read_bytes().splitlines()
            if isinstance(json.loads(line), dict) and json.loads(line).get("event") == "instance_correction"
        ]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        correction_lines = []
    if correction_lines != [expected_log]:
        errors.append("correction_instance:decision_log_evidence_mismatch")
    return errors


def _post_shape_label(event: dict[str, object], receipt_ids: dict[str, str]) -> str | None:
    request_id = event.get("request_id")
    for name, value in receipt_ids.items():
        if request_id == value:
            summary = event.get("request_summary")
            if name == "principal_schema_dry_run":
                return name if _is_principal_schema_batch(summary, "dry_run") else "invalid_principal_schema_batch"
            if name == "shape_apply":
                return name if _is_principal_schema_batch(summary, "apply_atomic") else "invalid_principal_schema_batch"
            if name in {REJECTION_RECEIPT, "valid_instance_dry_run"}:
                return name if _is_instance_batch(summary, "dry_run") else "invalid_instance_batch"
            if name in {FIRST_INSTANCE_APPLY_RECEIPT, CORRECTION_APPLY_RECEIPT}:
                return name if _is_instance_batch(summary, "apply_atomic") else "invalid_instance_batch"
            if name == CORRECTION_DRY_RECEIPT:
                return name if _is_instance_batch(summary, "dry_run") else "invalid_instance_batch"
            return name
    path, method = event.get("path"), event.get("method")
    summary = event.get("request_summary")
    if path and method == "POST" and isinstance(summary, dict) and str(path).endswith("/modeling-batches"):
        kinds = summary.get("command_kinds")
        if isinstance(kinds, list) and set(kinds).intersection(SCHEMA_COMMAND_KINDS):
            return "forbidden_schema_batch"
        if summary.get("mode") == "dry_run":
            return "valid_instance_dry_run"
        if summary.get("mode") == "apply_atomic":
            return "valid_instance_apply"
    return "forbidden_post_shape_operation"


def _timeline_errors(
    events: list[dict[str, object]], receipts: dict[str, object], runner_started_at: datetime | None
) -> list[str]:
    receipt_ids = {
        name: value.get("request_id")
        for name, value in receipts.items()
        if isinstance(value, dict) and isinstance(value.get("request_id"), str)
    }
    principal_request_id = receipt_ids.get("principal_schema_dry_run")
    if not principal_request_id:
        return ["timeline:missing_principal_schema_dry_run"]
    principal_index = next(
        (index for index, event in enumerate(events) if event.get("request_id") == principal_request_id), None
    )
    if principal_index is None:
        return ["timeline:principal_schema_dry_run_not_forwarded"]
    instance_tail = (
        ["valid_instance_apply"]
        if FIRST_INSTANCE_APPLY_RECEIPT in receipt_ids
        else [CORRECTION_DRY_RECEIPT, CORRECTION_APPLY_RECEIPT]
    )
    expected = [
        "principal_schema_dry_run",
        "shape_apply",
        "invalid_shape_dry_run",
        "valid_instance_dry_run",
        *instance_tail,
        "validation",
        "reasoning",
        "governed_query",
        "pre_checkpoint_get",
        "checkpoint",
        "complete",
        "final_get",
    ]
    errors: list[str] = []
    if any(_is_pre_principal_probe(event) for event in events[:principal_index]):
        errors.append("timeline:pre_principal_probe")
    labels: list[str] = []
    for event in events[principal_index:]:
        label = _post_shape_label(event, receipt_ids)
        labels.append(label or "forbidden_post_shape_operation")
    if labels != expected:
        errors.append("timeline:closed_sequence_violation")
    if labels == expected:
        dry_summary = events[principal_index + 3].get("request_summary")
        apply_offset = 4 if FIRST_INSTANCE_APPLY_RECEIPT in receipt_ids else 5
        apply_summary = events[principal_index + apply_offset].get("request_summary")
        if (
            not isinstance(dry_summary, dict)
            or not isinstance(apply_summary, dict)
            or (FIRST_INSTANCE_APPLY_RECEIPT in receipt_ids and dry_summary.get("client_batch_id") != apply_summary.get("client_batch_id"))
            or (FIRST_INSTANCE_APPLY_RECEIPT in receipt_ids and dry_summary.get("items_sha256") != apply_summary.get("items_sha256"))
        ):
            errors.append("timeline:valid_instance_apply_not_matching_dry_run")
    if runner_started_at is None:
        return [*errors, "timeline:missing_runner_start"]
    event_by_label = {label: event for label, event in zip(labels, events[principal_index:], strict=True)}
    core_labels = expected[:10]
    for label in core_labels:
        event_time = _event_time(event_by_label.get(label, {}))
        if event_time is None or event_time > runner_started_at + timedelta(seconds=600):
            errors.append(f"timeline:{label}_outside_core_window")
    for label in expected[8:]:
        event_time = _event_time(event_by_label.get(label, {}))
        if (
            event_time is None
            or event_time < runner_started_at
            or event_time > runner_started_at + timedelta(seconds=660)
        ):
            errors.append(f"timeline:{label}_outside_tail_window")
    return errors


def _completion_gate(
    paths: dict[str, Path], runtime: dict[str, object], forwarded: dict[str, dict[str, object]], run_tag: str
) -> list[str]:
    errors: list[str] = []
    if runtime.get("run_tag") != run_tag:
        errors.append("runtime_run_tag_mismatch")
    receipts = runtime.get("receipts")
    if not isinstance(receipts, dict):
        return ["missing_receipts"]
    for name in SUCCESS_RECEIPTS:
        reason = _receipt_matches_audit(receipts.get(name), forwarded, success=True)
        if reason:
            errors.append(f"{name}:{reason}")
    reason = _receipt_matches_audit(receipts.get(REJECTION_RECEIPT), forwarded, success=True)
    if reason:
        errors.append(f"{REJECTION_RECEIPT}:{reason}")
    dynamic_receipts = tuple(
        name
        for name in (FIRST_INSTANCE_APPLY_RECEIPT, CORRECTION_DRY_RECEIPT, CORRECTION_APPLY_RECEIPT)
        if name in receipts
    )
    for name in dynamic_receipts:
        reason = _receipt_matches_audit(receipts.get(name), forwarded, success=True)
        if reason:
            errors.append(f"{name}:{reason}")
    bodies: dict[str, dict[str, object]] = {}
    audits: dict[str, dict[str, object]] = {}
    for name in (*SUCCESS_RECEIPTS, REJECTION_RECEIPT, *dynamic_receipts):
        body, audit, response_error = _gateway_response_body(paths, receipts.get(name), forwarded)
        if response_error:
            errors.append(f"{name}:{response_error}")
        elif body is not None and audit is not None:
            bodies[name], audits[name] = body, audit

    session_ids: set[str] = set()
    for name, audit in audits.items():
        session_id, endpoint_error = _endpoint_session_id(name, audit)
        if endpoint_error:
            errors.append(f"{name}:{endpoint_error}")
        elif session_id and name in {
            "principal_schema_dry_run",
            "shape_apply",
            REJECTION_RECEIPT,
            "valid_instance_dry_run",
            FIRST_INSTANCE_APPLY_RECEIPT,
            CORRECTION_DRY_RECEIPT,
            CORRECTION_APPLY_RECEIPT,
            "pre_checkpoint_get",
            "checkpoint",
            "complete",
            "final_get",
        }:
            session_ids.add(session_id)
    if len(session_ids) != 1:
        errors.append("build_session_endpoint_mismatch")

    principal_schema_dry_run = bodies.get("principal_schema_dry_run", {})
    principal_request = audits.get("principal_schema_dry_run", {}).get("request_summary")
    shape_apply = bodies.get("shape_apply", {})
    shape_request = audits.get("shape_apply", {}).get("request_summary")
    if (
        principal_schema_dry_run.get("mode") != "dry_run"
        or principal_schema_dry_run.get("attempt_status") != "validated"
        or not isinstance(principal_request, dict)
        or not _is_principal_schema_batch(principal_request, "dry_run")
        or shape_apply.get("mode") != "apply_atomic"
        or shape_apply.get("attempt_status") != "applied"
        or shape_apply.get("batch_status") != "applied"
        or not isinstance(shape_request, dict)
        or not _is_principal_schema_batch(shape_request, "apply_atomic")
        or principal_request.get("client_batch_id") != shape_request.get("client_batch_id")
        or principal_request.get("items_sha256") != shape_request.get("items_sha256")
    ):
        errors.append("principal_schema:not_matching_validated_shape_batch")

    rejected = bodies.get(REJECTION_RECEIPT, {})
    findings = rejected.get("findings")
    rejected_receipt = receipts.get(REJECTION_RECEIPT)
    rejected_request = audits.get(REJECTION_RECEIPT, {}).get("request_summary")
    if (
        not isinstance(rejected_receipt, dict)
        or rejected_receipt.get("status") != 200
        or rejected.get("mode") != "dry_run"
        or rejected.get("attempt_status") != "validation_failed"
        or rejected.get("batch_status") == "applied"
        or not isinstance(rejected_request, dict)
        or not _is_instance_batch(rejected_request, "dry_run")
        or not isinstance(findings, list)
        or not any(
        isinstance(finding, dict)
        and finding.get("code") == "shacl_violation"
        and finding.get("blocking") is True
        for finding in findings
        )
    ):
        errors.append("invalid_shape_dry_run:not_shacl_validation_failure")
    validation = bodies.get("validation", {})
    if validation.get("conforms") is not True:
        errors.append("validation:not_conformant")
    reasoning = bodies.get("reasoning", {})
    pointer = reasoning.get("derived_pointer")
    if reasoning.get("status") != "succeeded" or reasoning.get("consistent") is not True:
        errors.append("reasoning:not_consistent")
    if not isinstance(pointer, dict) or pointer.get("status") != "current":
        errors.append("reasoning:not_current_pointer")
    graph_set_id, _ = _endpoint_session_id("reasoning", audits.get("reasoning", {}))
    if graph_set_id is None or not isinstance(pointer, dict) or pointer.get("graph_set_id") != graph_set_id:
        errors.append("reasoning:graph_set_pointer_mismatch")
    valid_dry = bodies.get("valid_instance_dry_run", {})
    valid_dry_summary = audits.get("valid_instance_dry_run", {}).get("request_summary")
    if not isinstance(valid_dry_summary, dict) or not _is_instance_batch(valid_dry_summary, "dry_run"):
        errors.append("valid_instance:invalid_first_candidate")
        errors.append("valid_instance:not_matching_validated_apply")
    first_apply = bodies.get(FIRST_INSTANCE_APPLY_RECEIPT, {})
    first_apply_summary = audits.get(FIRST_INSTANCE_APPLY_RECEIPT, {}).get("request_summary")
    correction_dry = bodies.get(CORRECTION_DRY_RECEIPT, {})
    correction_apply = bodies.get(CORRECTION_APPLY_RECEIPT, {})
    correction_dry_summary = audits.get(CORRECTION_DRY_RECEIPT, {}).get("request_summary")
    correction_apply_summary = audits.get(CORRECTION_APPLY_RECEIPT, {}).get("request_summary")
    if valid_dry.get("attempt_status") == "validated":
        if FIRST_INSTANCE_APPLY_RECEIPT not in receipts:
            errors.append(f"{FIRST_INSTANCE_APPLY_RECEIPT}:missing_or_invalid_receipt")
        if CORRECTION_DRY_RECEIPT in receipts or CORRECTION_APPLY_RECEIPT in receipts or (
            first_apply.get("mode") != "apply_atomic"
            or first_apply.get("attempt_status") != "applied"
            or first_apply.get("batch_status") != "applied"
            or not isinstance(first_apply_summary, dict)
            or not _is_instance_batch(first_apply_summary, "apply_atomic")
            or first_apply_summary.get("client_batch_id") != valid_dry_summary.get("client_batch_id")
            or first_apply_summary.get("items_sha256") != valid_dry_summary.get("items_sha256")
        ):
            errors.append("valid_instance:not_matching_validated_apply")
        errors.extend(
            _modeling_target_errors(
                principal_schema_dry_run,
                shape_apply,
                rejected,
                valid_dry,
                first_apply,
            )
        )
    elif _qualifying_instance_failure(valid_dry):
        if FIRST_INSTANCE_APPLY_RECEIPT in receipts or (
            correction_dry.get("attempt_status") != "validated"
            or correction_dry.get("mode") != "dry_run"
            or correction_apply.get("attempt_status") != "applied"
            or correction_apply.get("mode") != "apply_atomic"
            or correction_apply.get("batch_status") != "applied"
            or not isinstance(correction_dry_summary, dict)
            or not isinstance(correction_apply_summary, dict)
            or not _is_instance_batch(correction_dry_summary, "dry_run")
            or not _is_instance_batch(correction_apply_summary, "apply_atomic")
            or correction_dry_summary.get("client_batch_id") == valid_dry_summary.get("client_batch_id")
            or correction_dry_summary.get("items_sha256") == valid_dry_summary.get("items_sha256")
            or correction_dry_summary.get("client_batch_id") != correction_apply_summary.get("client_batch_id")
            or correction_dry_summary.get("items_sha256") != correction_apply_summary.get("items_sha256")
            or correction_dry_summary.get("idempotency_key_sha256") == valid_dry_summary.get("idempotency_key_sha256")
            or correction_apply_summary.get("idempotency_key_sha256") == correction_dry_summary.get("idempotency_key_sha256")
            or any(
                correction_dry_summary.get(key) != valid_dry_summary.get(key)
                for key in ("ontology_id", "expected_workspace_version")
            )
            or any(
                correction_apply_summary.get(key) != correction_dry_summary.get(key)
                for key in ("ontology_id", "expected_workspace_version")
            )
        ):
            errors.append("correction_instance:invalid_or_unapplied")
        errors.extend(
            _modeling_target_errors(
                principal_schema_dry_run,
                shape_apply,
                rejected,
                valid_dry,
                correction_dry,
                correction_apply,
            )
        )
        errors.extend(
            _correction_evidence_errors(
                paths,
                runtime,
                receipts,
                valid_dry,
                valid_dry_summary,
                correction_dry_summary,
                correction_apply_summary,
            )
        )
    else:
        errors.append("valid_instance:unqualified_failure")
        errors.append("valid_instance:not_matching_validated_apply")
    query = bodies.get("governed_query", {})
    query_summary = audits.get("governed_query", {}).get("request_summary")
    query_scope = query.get("scope")
    ontologies = query_scope.get("ontologies") if isinstance(query_scope, dict) else None
    query_ontology_ids = query_summary.get("ontology_ids") if isinstance(query_summary, dict) else None
    ontology = ontologies[0] if isinstance(ontologies, list) and len(ontologies) == 1 else None
    derived_state = ontology.get("derived_state") if isinstance(ontology, dict) else None
    reasoning_state = derived_state.get("reasoning") if isinstance(derived_state, dict) else None
    rule_state = derived_state.get("rule") if isinstance(derived_state, dict) else None
    exact_optional_rule_warning = [
        {"code": "derived_result_missing", "message": "No current rule result pointer."}
    ]
    if (
        not _positive_query_result(query.get("result"))
        or query.get("truncated") is not False
        or query.get("warnings") != exact_optional_rule_warning
        or not isinstance(query_scope, dict)
        or query_scope.get("status") != "complete"
        or query_scope.get("excluded_ontologies") != []
        or not isinstance(query_ontology_ids, list)
        or len(query_ontology_ids) != 1
        or not isinstance(ontology, dict)
        or ontology.get("ontology_id") != query_ontology_ids[0]
        or not isinstance(reasoning_state, dict)
        or reasoning_state.get("status") != "current"
        or reasoning_state.get("run_id") != reasoning.get("run_id")
        or not isinstance(rule_state, dict)
        or rule_state.get("status") != "missing"
    ):
        errors.append("governed_query:invalid_optional_rule_absent_scope")
    optional_rule_absent = runtime.get("optional_rule_absent")
    query_receipt = receipts.get("governed_query")
    if (
        not isinstance(optional_rule_absent, dict)
        or optional_rule_absent.get("code") != "derived_result_missing"
        or optional_rule_absent.get("message") != "No current rule result pointer."
        or not isinstance(query_receipt, dict)
        or optional_rule_absent.get("request_id") != query_receipt.get("request_id")
        or optional_rule_absent.get("response_sha256") != query_receipt.get("raw_response_sha256")
    ):
        errors.append("governed_query:missing_optional_rule_absent_decision")

    checkpoint = runtime.get("checkpoint")
    completion = runtime.get("build_session_completion")
    checkpoint_body = bodies.get("checkpoint", {})
    checkpoint_response = checkpoint_body.get("checkpoint")
    checkpoint_session = checkpoint_body.get("session")
    if (
        not isinstance(checkpoint, dict)
        or not isinstance(checkpoint.get("id"), str)
        or not isinstance(checkpoint.get("session_revision"), int)
    ):
        errors.append("missing_checkpoint")
        return errors
    if not isinstance(completion, dict):
        errors.append("missing_build_session_completion")
        return errors
    checkpoint_id = checkpoint["id"]
    pre_checkpoint_get = bodies.get("pre_checkpoint_get", {})
    pre_checkpoint_session = pre_checkpoint_get.get("session")
    checkpoint_audit = audits.get("checkpoint", {})
    checkpoint_summary = checkpoint_audit.get("request_summary")
    pre_checkpoint_session_id, _ = _endpoint_session_id("pre_checkpoint_get", audits.get("pre_checkpoint_get", {}))
    checkpoint_session_id, _ = _endpoint_session_id("checkpoint", checkpoint_audit)
    if (
        not isinstance(pre_checkpoint_session, dict)
        or pre_checkpoint_session.get("id") != pre_checkpoint_session_id
        or pre_checkpoint_session_id != checkpoint_session_id
        or not isinstance(checkpoint_summary, dict)
        or checkpoint_summary.get("expected_revision") != pre_checkpoint_session.get("revision")
    ):
        errors.append("pre_checkpoint_get:session_revision_mismatch")
    if (
        not isinstance(checkpoint_response, dict)
        or checkpoint_response.get("id") != checkpoint_id
        or not isinstance(checkpoint_session, dict)
        or checkpoint.get("session_revision") != checkpoint_session.get("revision")
    ):
        errors.append("checkpoint_response_mismatch")
    complete_audit = audits.get("complete", {})
    complete_summary = complete_audit.get("request_summary")
    if (
        not isinstance(complete_summary, dict)
        or complete_summary.get("expected_revision") != checkpoint.get("session_revision")
    ):
        errors.append("complete_expected_revision_mismatch")
    complete_body = bodies.get("complete", {})
    if complete_body.get("status") != "completed" or not isinstance(complete_body.get("revision"), int):
        errors.append("complete_response_not_completed")
    final_get_body = bodies.get("final_get", {})
    final_session = final_get_body.get("session")
    final_checkpoint = final_get_body.get("latest_checkpoint")
    if (
        not isinstance(final_session, dict)
        or final_session.get("status") != "completed"
        or not isinstance(final_session.get("completed_at"), str)
        or not isinstance(final_checkpoint, dict)
        or final_checkpoint.get("id") != checkpoint_id
    ):
        errors.append("final_get_not_completed_or_checkpoint_mismatch")
    if completion.get("latest_checkpoint_id") != checkpoint_id:
        errors.append("checkpoint_id_mismatch")
    if completion.get("status") != "completed" or not isinstance(completion.get("completed_at"), str):
        errors.append("build_session_not_completed")
    for name, receipt_name in (("complete_request_id", "complete"), ("final_get_request_id", "final_get")):
        receipt = receipts.get(receipt_name)
        if not isinstance(receipt, dict) or completion.get(name) != receipt.get("request_id"):
            errors.append(f"{name}_mismatch")
    return errors


def _final_audit(
    paths: dict[str, Path],
    run_tag: str,
    agent_exit_code: int,
    canonical_mode: dict[str, object],
    runner_started_at: datetime | None = None,
) -> dict[str, object]:
    transcript = paths["transcript"].read_bytes() if paths["transcript"].exists() else b""
    runtime_record = paths["workspace"] / "runtime-record.json"
    decision_log = paths["workspace"] / "decision-log.jsonl"
    forbidden = [b"/home/yangxiang/projects/ontology-platform", b"/mnt/host"]
    runtime_value, runtime_error = _load_json_object(runtime_record)
    events, forwarded, api_audit_error = _forwarded_api_receipts(paths["api_audit"])
    if runner_started_at is None and events:
        runner_started_at = _event_time(events[0])
    audit: dict[str, object] = {
        "run_tag": run_tag,
        "agent_exit_code": agent_exit_code,
        "canonical_mode": canonical_mode,
        "transcript_sha256": sha256_bytes(transcript),
        "transcript_forbidden_host_path": any(item in transcript for item in forbidden),
        "clarification_requests": _response_inventory(paths["clarification_requests"]),
        "clarification_responses": _response_inventory(paths["clarification_responses"]),
        "api_requests": _response_inventory(paths["api_requests"]),
        "api_responses": _response_inventory(paths["api_responses"]),
        "clarification_audit_sha256": sha256(paths["host_audit"]) if paths["host_audit"].exists() else None,
        "api_audit_sha256": sha256(paths["api_audit"]) if paths["api_audit"].exists() else None,
        "runtime_record_sha256": sha256(runtime_record) if runtime_record.is_file() else None,
        "decision_log_sha256": sha256(decision_log) if decision_log.is_file() else None,
        "runtime_record_error": runtime_error,
        "api_audit_error": api_audit_error,
        "runner_started_at": runner_started_at.isoformat() if runner_started_at else None,
    }
    terminal_status = runtime_value.get("terminal_status") if runtime_value else None
    audit["runtime_terminal_status"] = terminal_status
    if terminal_status in {"BLOCKED", "INCONCLUSIVE"}:
        audit["status"] = terminal_status
        audit["completion_gate_errors"] = []
    elif terminal_status != "DEVELOPMENT_READY":
        audit["status"] = "INCONCLUSIVE"
        audit["completion_gate_errors"] = ["invalid_runtime_terminal_status"]
    else:
        gate_errors = _completion_gate(paths, runtime_value, forwarded, run_tag)
        gate_errors.extend(_clarification_timeline_errors(paths, events, run_tag))
        gate_errors.extend(_timeline_errors(events, runtime_value.get("receipts", {}), runner_started_at))
        optional_rule_absent = runtime_value.get("optional_rule_absent")
        if isinstance(optional_rule_absent, dict):
            audit["optional_rule_absent"] = {
                key: optional_rule_absent.get(key)
                for key in ("request_id", "response_sha256", "code", "message")
            }
        if agent_exit_code != 0:
            gate_errors.append("agent_exit_nonzero")
        if audit["transcript_forbidden_host_path"]:
            gate_errors.append("transcript_forbidden_host_path")
        if audit["decision_log_sha256"] is None:
            gate_errors.append("missing_decision_log")
        if runtime_error or api_audit_error:
            gate_errors.append("runtime_or_api_audit_invalid")
        audit["completion_gate_errors"] = gate_errors
        audit["status"] = "COMPLETED" if not gate_errors else "INCONCLUSIVE"
    paths["run_audit"].write_bytes(canonical_json(audit))
    os.chmod(paths["run_audit"], 0o400)
    return audit


def run_formal(
    run_root: Path, variant: str, run_tag: str, *, backend_port: int = 8012, timeout_seconds: int = 1800
) -> dict[str, object]:
    """Execute a real fresh Codex process while both host spools serve its isolated namespace."""
    if timeout_seconds <= 0:
        raise IsolationError("timeout seconds must be positive")
    api_key = load_api_key()
    canonical_mode = verify_isolated_write_mode(api_key, backend_port)
    paths, mount_audit = _prepare_execution(run_root, variant, run_tag)
    prepare_codex_home(paths)
    host_environment = {**os.environ, "M4_HOST_API_KEY": api_key}
    responder = subprocess.Popen(responder_command(paths, watch=True), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    gateway = subprocess.Popen(
        api_gateway_command(paths, backend_port, watch=True),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env=host_environment,
    )
    exit_code = 125
    runner_started_at = datetime.now(UTC)
    try:
        prompt = (paths["staging"] / "modeling-agent-prompt.md").read_bytes()
        with paths["transcript"].open("wb") as transcript, paths["stderr"].open("wb") as stderr:
            result = subprocess.run(
                agent_command(paths, run_tag),
                input=prompt,
                stdout=transcript,
                stderr=stderr,
                timeout=timeout_seconds,
                check=False,
            )
            exit_code = result.returncode
    except subprocess.TimeoutExpired:
        exit_code = 124
    finally:
        _terminate(responder)
        _terminate(gateway)
    final_audit = _final_audit(paths, run_tag, exit_code, canonical_mode, runner_started_at)
    return {
        "status": final_audit["status"],
        "run_tag": run_tag,
        "mount_audit": mount_audit,
        "final_audit": final_audit,
        "run_root": str(run_root),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--variant", choices=("baseline", "pinned-non-successor"), required=True)
    parser.add_argument("--run-tag", default="m4-clarification-run")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--backend-port", type=int, default=8012)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    args = parser.parse_args()
    result = (
        prepare_run(args.run_root, args.variant, args.run_tag)
        if args.prepare_only
        else run_formal(
            args.run_root,
            args.variant,
            args.run_tag,
            backend_port=args.backend_port,
            timeout_seconds=args.timeout_seconds,
        )
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except IsolationError as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2) from error
