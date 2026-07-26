#!/usr/bin/env python3
"""Launch one fresh, auditable, isolated R2.1-001 M3 modeling Agent."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

SCENARIO_ROOT: Final = Path(__file__).resolve().parent
REPOSITORY_ROOT: Final = SCENARIO_ROOT.parents[2]
MANIFEST_PATH: Final = SCENARIO_ROOT / "input-pack" / "input-manifest.json"
FROZEN_MANIFEST_SHA256: Final = "4cf3eb32e41f0ab82cbcb5ef07b76d3bd7611c015bfbca41d35db14b2f521b1b"
CODEX_BINARY: Final = Path("/home/yangxiang/.local/bin/codex")
HOST_CODEX_AUTH: Final = Path("/home/yangxiang/.codex/auth.json")
GATEWAY_SCRIPT: Final = SCENARIO_ROOT / "m3_file_spool_gateway.py"
RUN_TAG_RE: Final = re.compile(r"^[a-z0-9][a-z0-9-]{2,80}$")
RECEIPT_FILENAME: Final = "spool-consumption-receipts.jsonl"
RECEIPT_KEYS: Final = {
    "run_tag",
    "request_id",
    "response_id",
    "canonical_request_sha256",
    "host_response_sha256",
    "status",
    "response_read_confirmed",
}
BUILD_COMPLETION_KEYS: Final = {
    "run_tag",
    "checkpoint_id",
    "checkpoint_request_id",
    "complete_request_id",
    "final_session_read_request_id",
    "status",
    "completed_at",
}
FORBIDDEN_HOST_PATH_RE: Final = re.compile(
    rb"/home/yangxiang/(?:projects/ontology-platform|\.codex)(?:/|\b)"
)


class IsolationError(RuntimeError):
    """The run is not admissible when this is raised."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def read_manifest() -> dict[str, Any]:
    actual = sha256(MANIFEST_PATH)
    if actual != FROZEN_MANIFEST_SHA256:
        raise IsolationError(f"frozen manifest SHA-256 mismatch: {actual}")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("mount_policy") != "copy each listed file to its mounted_path; never mount a source directory":
        raise IsolationError("unexpected manifest mount policy")
    return manifest


def relative_path(value: str, label: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not value:
        raise IsolationError(f"unsafe {label}: {value!r}")
    return path


def verify_and_stage(manifest: dict[str, Any], staging: Path) -> dict[str, Any]:
    staging.mkdir(mode=0o700, parents=True, exist_ok=False)
    staged_manifest = staging / "input-manifest.json"
    shutil.copyfile(MANIFEST_PATH, staged_manifest)
    os.chmod(staged_manifest, 0o444)
    declared = {"input-manifest.json"}
    hashes: list[dict[str, str]] = []
    for item in manifest["files"]:
        source_path = relative_path(item["source_path"], "source_path")
        mounted_path = relative_path(item["mounted_path"], "mounted_path")
        if mounted_path.as_posix() in declared:
            raise IsolationError(f"duplicate staged mount path: {mounted_path}")
        source = (REPOSITORY_ROOT / source_path).resolve()
        if REPOSITORY_ROOT not in source.parents:
            raise IsolationError(f"source escapes repository: {source_path}")
        expected = item["sha256"]
        if sha256(source) != expected:
            raise IsolationError(f"source hash mismatch for {source_path}")
        target = staging / mounted_path
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        os.chmod(target, 0o444)
        if sha256(target) != expected:
            raise IsolationError(f"staged hash mismatch for {mounted_path}")
        declared.add(mounted_path.as_posix())
        hashes.append({"source_path": source_path.as_posix(), "mounted_path": mounted_path.as_posix(), "sha256": expected})
    actual_set = {path.relative_to(staging).as_posix() for path in staging.rglob("*") if path.is_file()}
    if actual_set != declared or sha256(staged_manifest) != FROZEN_MANIFEST_SHA256:
        raise IsolationError("staged file set or manifest hash differs from the frozen contract")
    return {"declared_mount_set": sorted(declared), "file_hashes": hashes}


def load_api_key() -> str:
    for line in (REPOSITORY_ROOT / "backend" / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("ONTOLOGY_MCP_API_KEY="):
            value = line.partition("=")[2].strip().strip("\"'")
            if value:
                return value
    raise IsolationError("backend/.env has no ONTOLOGY_MCP_API_KEY")


def host_canonical_mode(api_key: str) -> dict[str, object]:
    connection = http.client.HTTPConnection("127.0.0.1", 8012, timeout=30)
    connection.request("GET", "/api/semantic/canonical-mode", headers={"Authorization": f"Bearer {api_key}"})
    response = connection.getresponse()
    payload = json.loads(response.read().decode("utf-8"))
    if response.status != 200 or payload.get("product_write_mode") != "rdf_primary":
        raise IsolationError("isolated backend is not rdf_primary")
    return payload


def bwrap_command(
    *, staging: Path, workspace: Path, codex_home: Path, responses: Path, run_tag: str
) -> list[str]:
    command = [
        "bwrap", "--die-with-parent", "--new-session", "--unshare-user", "--unshare-pid", "--unshare-ipc",
        "--unshare-uts", "--share-net", "--clearenv",
    ]
    for source in ("/usr", "/bin", "/lib", "/lib64", "/etc/ssl", "/etc/nsswitch.conf", "/etc/hosts", "/etc/resolv.conf"):
        if Path(source).exists():
            command.extend(["--ro-bind", source, source])
    command.extend(
        [
            "--ro-bind", str(CODEX_BINARY.resolve()), "/codex", "--ro-bind", str(staging), "/opt",
            "--bind", str(workspace), "/mnt", "--bind", str(codex_home), "/codex-home",
            "--ro-bind", str(responses), "/mnt/rpc/responses", "--dev", "/dev", "--proc", "/proc",
            "--tmpfs", "/tmp", "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "HOME", "/tmp",
            "--setenv", "CODEX_HOME", "/codex-home", "--setenv", "M3_API_REQUEST_DIR", "/mnt/rpc/requests",
            "--setenv", "M3_API_RESPONSE_DIR", "/mnt/rpc/responses", "--setenv", "NO_PROXY", "127.0.0.1,localhost",
            "--setenv", "M3_RUN_TAG", run_tag,
        ]
    )
    for name in ("HTTPS_PROXY", "HTTP_PROXY"):
        if os.environ.get(name):
            command.extend(["--setenv", name, os.environ[name]])
    command.extend(
        [
            "--", "/codex", "exec", "--json", "--ephemeral", "--ignore-user-config", "--ignore-rules",
            "--skip-git-repo-check", "--sandbox", "workspace-write", "--disable", "apps", "--disable",
            "browser_use", "--disable", "browser_use_external", "--disable", "computer_use", "--disable",
            "in_app_browser", "--disable", "standalone_web_search", "--disable", "plugins", "--disable",
            "memories", "-C", "/mnt", "-",
        ]
    )
    return command


def isolation_probe(command: list[str]) -> dict[str, object]:
    probe = command[: command.index("--")] + [
        "--", "/bin/sh", "-c",
        "test ! -e /home/yangxiang/projects/ontology-platform && test ! -e /home/yangxiang/.codex && test -f /opt/input-manifest.json && test -w /mnt/rpc/requests && test ! -w /mnt/rpc/responses",
    ]
    result = subprocess.run(probe, check=False, capture_output=True, text=True, timeout=30)
    return {"exit_code": result.returncode, "passed": result.returncode == 0, "stderr": result.stderr.strip()}


def forbidden_commands(transcript: Path) -> bool:
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            item = json.loads(line).get("item", {})
        except json.JSONDecodeError:
            continue
        command = item.get("command") if isinstance(item, dict) else None
        if isinstance(command, str) and FORBIDDEN_HOST_PATH_RE.search(command.encode()):
            return True
    return False


def scan_files(
    paths: list[Path], secret: str, *, scan_host_paths: bool = True
) -> dict[str, object]:
    secret_found, forbidden, count = False, [], 0
    for root in paths:
        files = [root] if root.is_file() else [path for path in root.rglob("*") if path.is_file()]
        for path in files:
            count += 1
            data = path.read_bytes()
            secret_found = secret_found or secret.encode() in data
            bad = scan_host_paths and (
                forbidden_commands(path)
                if path.name == "agent-transcript.jsonl"
                else bool(FORBIDDEN_HOST_PATH_RE.search(data))
            )
            if bad:
                forbidden.append(str(path.relative_to(root.parent)))
    return {"files_scanned": count, "secret_found": secret_found, "forbidden_host_path_files": forbidden, "passed": not secret_found and not forbidden}


def scan_run_artifacts(run_dir: Path, secret: str) -> dict[str, object]:
    """Audit Agent-controlled material separately from untrusted public API payloads."""
    agent_controlled = scan_files(
        [
            run_dir / "agent-transcript.jsonl",
            run_dir / "work",
            run_dir / "gateway-request-archive",
            run_dir / "codex-stderr.log",
        ],
        secret,
    )
    public_api = scan_files(
        [run_dir / "gateway-responses", run_dir / "gateway.jsonl"],
        secret,
        scan_host_paths=False,
    )
    forbidden = agent_controlled["forbidden_host_path_files"]
    return {
        "files_scanned": agent_controlled["files_scanned"] + public_api["files_scanned"],
        "secret_found": agent_controlled["secret_found"] or public_api["secret_found"],
        "forbidden_host_path_files": forbidden,
        "public_api_payloads_scanned_for_secret_only": public_api["files_scanned"],
        "passed": not (agent_controlled["secret_found"] or public_api["secret_found"] or forbidden),
    }


def agent_artifact_snapshot(run_dir: Path) -> dict[str, object]:
    """Compact immutable fingerprint of Agent and gateway evidence, excluding host recheck output."""
    paths = [
        run_dir / "agent-transcript.jsonl",
        run_dir / "work",
        run_dir / "gateway-responses",
        run_dir / "gateway-request-archive",
        run_dir / "gateway.jsonl",
        run_dir / "codex-stderr.log",
    ]
    entries: list[dict[str, object]] = []
    for root in paths:
        files = [root] if root.is_file() else [path for path in root.rglob("*") if path.is_file()]
        for path in sorted(files):
            info = path.stat()
            entries.append(
                {
                    "path": path.relative_to(run_dir).as_posix(),
                    "sha256": sha256(path),
                    "size": info.st_size,
                    "mtime_ns": info.st_mtime_ns,
                }
            )
    return {"files": len(entries), "fingerprint_sha256": sha256_bytes(canonical_json(entries))}


def receipt_audit(run_dir: Path, run_tag: str) -> dict[str, object]:
    """Fail closed unless Agent receipts prove every forwarded response was consumed."""
    errors: list[str] = []
    forwarded: dict[str, dict[str, object]] = {}
    audit_path = run_dir / "gateway.jsonl"
    try:
        audit_entries = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    except (OSError, json.JSONDecodeError) as error:
        return {"passed": False, "errors": [f"invalid gateway audit: {type(error).__name__}"], "forwarded_count": 0}
    for entry in audit_entries:
        if entry.get("policy") != "forwarded":
            continue
        request_id = entry.get("request_id")
        if not isinstance(request_id, str) or request_id in forwarded:
            errors.append("gateway audit has invalid or duplicate forwarded request ID")
            continue
        forwarded[request_id] = entry
    receipt_path = run_dir / "work" / RECEIPT_FILENAME
    receipts: dict[str, dict[str, object]] = {}
    receipt_log_sha256: str | None = None
    try:
        receipt_log_sha256 = sha256(receipt_path)
        for line_number, line in enumerate(receipt_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line:
                raise IsolationError(f"blank receipt line {line_number}")
            receipt = json.loads(line)
            if not isinstance(receipt, dict) or set(receipt) != RECEIPT_KEYS:
                raise IsolationError(f"receipt keys do not match on line {line_number}")
            if line.encode("utf-8") != canonical_json(receipt):
                raise IsolationError(f"receipt is not canonical JSON on line {line_number}")
            request_id = receipt.get("request_id")
            if not isinstance(request_id, str) or request_id in receipts:
                raise IsolationError(f"invalid or duplicate receipt ID on line {line_number}")
            receipts[request_id] = receipt
    except (OSError, json.JSONDecodeError, IsolationError) as error:
        errors.append(f"invalid Agent receipt log: {type(error).__name__}")
    if set(receipts) != set(forwarded):
        errors.append("receipt IDs do not exactly match forwarded gateway IDs")
    for request_id, entry in forwarded.items():
        receipt = receipts.get(request_id)
        archive = run_dir / "gateway-request-archive" / f"{request_id}.json"
        response = run_dir / "gateway-responses" / f"{request_id}.json"
        try:
            archive_sha256, response_sha256 = sha256(archive), sha256(response)
        except OSError:
            errors.append(f"missing host artifact for {request_id}")
            continue
        if archive_sha256 != entry.get("request_sha256") or response_sha256 != entry.get("response_sha256"):
            errors.append(f"host artifact hash mismatch for {request_id}")
        if receipt is None:
            continue
        if (
            receipt.get("run_tag") != run_tag
            or receipt.get("response_id") != request_id
            or receipt.get("canonical_request_sha256") != archive_sha256
            or receipt.get("host_response_sha256") != response_sha256
            or receipt.get("status") != entry.get("status")
            or receipt.get("response_read_confirmed") is not True
        ):
            errors.append(f"Agent receipt does not bind host response for {request_id}")
    runtime_path = run_dir / "work" / "runtime-record.json"
    try:
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        log = runtime.get("spool_receipt_log")
        runtime_receipts = runtime.get("spool_receipts")
        if runtime.get("run_tag") != run_tag:
            errors.append("runtime record run_tag differs from launcher run tag")
        if log != {"path": RECEIPT_FILENAME, "sha256": receipt_log_sha256, "count": len(receipts)}:
            errors.append("runtime record receipt log summary differs from Agent receipt log")
        if not isinstance(runtime_receipts, list) or runtime_receipts != list(receipts.values()):
            errors.append("runtime record receipt entries differ from Agent receipt log")
    except (OSError, json.JSONDecodeError):
        errors.append("runtime record is missing or invalid")
    transcript = run_dir / "agent-transcript.jsonl"
    summary = (
        f"M3_RECEIPT_SUMMARY run_tag={run_tag} receipt_count={len(receipts)} "
        f"receipt_log_sha256={receipt_log_sha256}"
    )
    try:
        if summary not in transcript.read_text(encoding="utf-8"):
            errors.append("Agent transcript lacks exact receipt summary")
    except OSError:
        errors.append("Agent transcript is missing")
    return {
        "passed": not errors,
        "errors": errors,
        "forwarded_count": len(forwarded),
        "receipt_count": len(receipts),
        "receipt_log_sha256": receipt_log_sha256,
    }


def build_session_audit(run_dir: Path, run_tag: str) -> dict[str, object]:
    """Prove the Agent checkpointed and completed its own fresh Build Session."""
    errors: list[str] = []
    try:
        runtime = json.loads((run_dir / "work" / "runtime-record.json").read_text(encoding="utf-8"))
        session_id = runtime.get("build_session_id") or runtime.get("session_id")
        completion = runtime.get("build_session_completion")
        if (
            runtime.get("build_session_id") is not None
            and runtime.get("session_id") is not None
            and runtime["build_session_id"] != runtime["session_id"]
        ):
            errors.append("runtime record has inconsistent Build Session IDs")
        if runtime.get("run_tag") != run_tag:
            errors.append("runtime record run_tag differs from launcher run tag")
        if not isinstance(session_id, str) or not session_id:
            errors.append("runtime record lacks Build Session ID")
        if not isinstance(completion, dict) or set(completion) != BUILD_COMPLETION_KEYS:
            errors.append("runtime record lacks exact Build Session completion evidence")
            return {"passed": False, "errors": errors}
        if completion.get("run_tag") != run_tag:
            errors.append("Build Session completion run_tag differs from launcher run tag")
    except (OSError, json.JSONDecodeError):
        return {"passed": False, "errors": ["runtime record is missing or invalid"]}
    try:
        entries = [json.loads(line) for line in (run_dir / "gateway.jsonl").read_text(encoding="utf-8").splitlines()]
    except (OSError, json.JSONDecodeError) as error:
        return {"passed": False, "errors": [f"invalid gateway audit: {type(error).__name__}"]}
    forwarded = {
        entry.get("request_id"): entry
        for entry in entries
        if entry.get("policy") == "forwarded" and isinstance(entry.get("request_id"), str)
    }

    def response_for(field: str, method: str, path: str) -> dict[str, object] | None:
        request_id = completion.get(field)
        entry = forwarded.get(request_id)
        if not isinstance(request_id, str) or entry is None:
            errors.append(f"completion evidence lacks forwarded {field}")
            return None
        if entry.get("method") != method or entry.get("path") != path or entry.get("status") != 200:
            errors.append(f"completion request contract mismatch for {field}")
            return None
        try:
            response = json.loads((run_dir / "gateway-responses" / f"{request_id}.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            errors.append(f"missing or invalid host response for {field}")
            return None
        if response.get("id") != request_id or response.get("status") != 200 or not isinstance(response.get("body"), dict):
            errors.append(f"host response envelope mismatch for {field}")
            return None
        return response["body"]

    if not isinstance(session_id, str):
        return {"passed": False, "errors": errors}
    checkpoint = response_for(
        "checkpoint_request_id", "POST", f"/api/build-sessions/{session_id}/checkpoints"
    )
    completed = response_for("complete_request_id", "POST", f"/api/build-sessions/{session_id}:complete")
    final = response_for("final_session_read_request_id", "GET", f"/api/build-sessions/{session_id}")
    checkpoint_id = completion.get("checkpoint_id")
    if not isinstance(checkpoint_id, str) or not checkpoint_id:
        errors.append("completion evidence lacks checkpoint ID")
    if checkpoint is not None:
        checkpoint_value = checkpoint.get("checkpoint")
        if not isinstance(checkpoint_value, dict) or checkpoint_value.get("id") != checkpoint_id:
            errors.append("checkpoint response does not bind recorded checkpoint ID")
    if completed is not None:
        if (
            completed.get("id") != session_id
            or completed.get("status") != "completed"
            or completed.get("completed_at") != completion.get("completed_at")
            or not completion.get("completed_at")
        ):
            errors.append("completion response does not prove completed session")
    if final is not None:
        final_session = final.get("session")
        latest = final.get("latest_checkpoint")
        if (
            not isinstance(final_session, dict)
            or final_session.get("id") != session_id
            or final_session.get("status") != "completed"
            or final_session.get("completed_at") != completion.get("completed_at")
            or not isinstance(latest, dict)
            or latest.get("id") != checkpoint_id
        ):
            errors.append("final Build Session read does not bind completed state and checkpoint")
    if completion.get("status") != "completed":
        errors.append("runtime record completion status is not completed")
    return {
        "passed": not errors,
        "errors": errors,
        "session_id": session_id,
        "checkpoint_id": checkpoint_id,
        "completed_at": completion.get("completed_at"),
    }


def process_tree_pids(root_pid: int) -> set[int]:
    parents: dict[int, int] = {}
    for status_path in Path("/proc").glob("[0-9]*/status"):
        try:
            lines = status_path.read_text(encoding="utf-8").splitlines()
            parents[int(status_path.parent.name)] = int(next(line.split()[1] for line in lines if line.startswith("PPid:")))
        except (OSError, StopIteration, ValueError):
            continue
    descendants, changed = {root_pid}, True
    while changed:
        changed = False
        for pid, parent in parents.items():
            if parent in descendants and pid not in descendants:
                descendants.add(pid)
                changed = True
    return descendants


def argv_secret_audit(root_pid: int, secret: str) -> dict[str, object]:
    checked = sorted(process_tree_pids(root_pid))
    found = any(secret.encode() in (Path("/proc") / str(pid) / "cmdline").read_bytes() for pid in checked if (Path("/proc") / str(pid) / "cmdline").exists())
    return {"checked_pids": checked, "secret_found": found, "passed": not found}


def agent_result(transcript: Path) -> str | None:
    values = re.findall(r"\b(DEVELOPMENT_READY|BLOCKED|INCONCLUSIVE)\b", transcript.read_text(encoding="utf-8", errors="replace"))
    return values[-1] if values else None


def append_execution_log(run_tag: str, outcome: str, audit: dict[str, object]) -> None:
    with (SCENARIO_ROOT / "execution-log.md").open("a", encoding="utf-8") as stream:
        stream.write(
            f"\n### {utc_now()} — `{run_tag}`\n\n"
            f"- Environment outcome: `{outcome}`; modeling-Agent declared result: `{audit.get('agent_declared_result') or 'not found'}`.\n"
            f"- Isolation evidence: `runtime/runs/{run_tag}/audit.json`; secret/path audit: `{'passed' if audit.get('artifact_audit', {}).get('passed') else 'failed'}`.\n"
            "- Operator intervention: `environment` only; no semantic-decision intervention.\n"
        )


def re_audit(run_tag: str) -> int:
    run_dir = SCENARIO_ROOT / "runtime" / "runs" / run_tag
    original = json.loads((run_dir / "audit.json").read_text(encoding="utf-8"))
    before = agent_artifact_snapshot(run_dir)
    api_key = load_api_key()
    artifact = scan_run_artifacts(run_dir, api_key)
    receipts = receipt_audit(run_dir, run_tag)
    build_session = build_session_audit(run_dir, run_tag)
    after = agent_artifact_snapshot(run_dir)
    effective = "INCONCLUSIVE"
    if (
        original.get("codex_exit_code") == 0
        and original.get("agent_declared_result") in {"DEVELOPMENT_READY", "BLOCKED"}
        and original.get("process_argv_audit", {}).get("passed")
        and artifact["passed"]
        and receipts["passed"]
        and build_session["passed"]
    ):
        effective = original["agent_declared_result"]
    result = {
        "run_tag": run_tag,
        "rechecked_at": utc_now(),
        "reason": "public API response fields are data, not Agent host filesystem access",
        "artifact_audit": artifact,
        "receipt_audit": receipts,
        "build_session_audit": build_session,
        "agent_artifact_immutability": {"passed": before == after, "before": before, "after": after},
        "effective_status": effective,
    }
    recheck_paths = sorted(run_dir.glob("audit-recheck*.json"))
    recheck_path = (
        run_dir / "audit-recheck.json"
        if not recheck_paths
        else run_dir / f"audit-recheck-{len(recheck_paths) + 1}.json"
    )
    recheck_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with (SCENARIO_ROOT / "execution-log.md").open("a", encoding="utf-8") as stream:
        stream.write(
            f"\n### {utc_now()} — `{run_tag}` audit correction\n\n"
            "- The first post-run path scan falsely treated public API response data as Agent host-path access.\n"
            f"- `{recheck_path.name}` rechecks host-path, credential, Agent-receipt and Build Session evidence; effective outcome: `{effective}`.\n"
        )
    print(json.dumps({"run_tag": run_tag, "status": effective, "audit": str(recheck_path)}))
    return 0 if effective in {"DEVELOPMENT_READY", "BLOCKED"} else 2


def create_codex_home(path: Path) -> list[str]:
    path.mkdir(mode=0o700)
    shutil.copyfile(HOST_CODEX_AUTH, path / "auth.json")
    os.chmod(path / "auth.json", 0o600)
    files = sorted(item.name for item in path.iterdir())
    if files != ["auth.json"]:
        raise IsolationError("fresh CODEX_HOME contains more than authentication")
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tag", default=f"m3-{uuid.uuid4().hex[:12]}")
    parser.add_argument("--re-audit-run")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=5400)
    args = parser.parse_args()
    if args.re_audit_run:
        if not RUN_TAG_RE.fullmatch(args.re_audit_run):
            raise SystemExit("run tag must contain lowercase letters, digits and hyphens only")
        return re_audit(args.re_audit_run)
    if not RUN_TAG_RE.fullmatch(args.run_tag):
        raise SystemExit("run tag must contain lowercase letters, digits and hyphens only")
    run_dir = SCENARIO_ROOT / "runtime" / "runs" / args.run_tag
    if run_dir.exists() or not CODEX_BINARY.exists() or not HOST_CODEX_AUTH.exists():
        raise SystemExit("run target exists or Codex authentication is unavailable")
    run_dir.mkdir(mode=0o700, parents=True)
    staging, workspace = run_dir / "staging", run_dir / "work"
    workspace.mkdir(mode=0o700)
    requests, response_target = workspace / "rpc" / "requests", workspace / "rpc" / "responses"
    requests.mkdir(mode=0o700, parents=True)
    response_target.mkdir(mode=0o700)
    responses, archive = run_dir / "gateway-responses", run_dir / "gateway-request-archive"
    responses.mkdir(mode=0o700)
    archive.mkdir(mode=0o700)
    transcript, audit_path = run_dir / "agent-transcript.jsonl", run_dir / "audit.json"
    codex_home = run_dir / "temporary-codex-home"
    audit: dict[str, object] = {"run_tag": args.run_tag, "started_at": utc_now(), "status": "INCONCLUSIVE"}
    gateway: subprocess.Popen[str] | None = None
    api_key = ""
    try:
        manifest = read_manifest()
        audit["manifest_sha256"] = FROZEN_MANIFEST_SHA256
        audit["staging"] = verify_and_stage(manifest, staging)
        audit["fresh_codex_home_before"] = create_codex_home(codex_home)
        api_key = load_api_key()
        audit["isolated_canonical_mode"] = host_canonical_mode(api_key)
        command = bwrap_command(
            staging=staging,
            workspace=workspace,
            codex_home=codex_home,
            responses=responses,
            run_tag=args.run_tag,
        )
        audit["mount_command"] = ["<inherited-proxy>" if value in {os.environ.get("HTTP_PROXY"), os.environ.get("HTTPS_PROXY")} else value for value in command]
        gateway = subprocess.Popen(
            [sys.executable, str(GATEWAY_SCRIPT), "--requests", str(requests), "--responses", str(responses), "--archive", str(archive), "--audit", str(run_dir / "gateway.jsonl")],
            env={"PATH": os.environ["PATH"], "M3_API_KEY": api_key}, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )
        time.sleep(0.1)
        if gateway.poll() is not None:
            raise IsolationError("file-spool gateway stopped during startup")
        audit["isolation_probe"] = isolation_probe(command)
        if not audit["isolation_probe"]["passed"]:
            raise IsolationError("bubblewrap isolation probe failed")
        if args.prepare_only:
            audit["status"] = "PREPARED"
            return 0
        with (staging / "modeling-agent-prompt.md").open("rb") as prompt, transcript.open("wb") as output, (run_dir / "codex-stderr.log").open("wb") as errors:
            agent = subprocess.Popen(command, stdin=prompt, stdout=output, stderr=errors)
            time.sleep(0.5)
            audit["process_argv_audit"] = argv_secret_audit(agent.pid, api_key)
            completed = agent.wait(timeout=args.timeout_seconds)
        audit["codex_exit_code"] = completed
        audit["agent_declared_result"] = agent_result(transcript)
        audit["receipt_audit"] = receipt_audit(run_dir, args.run_tag)
        audit["build_session_audit"] = build_session_audit(run_dir, args.run_tag)
        audit["artifact_audit"] = scan_run_artifacts(run_dir, api_key)
        if (
            completed == 0
            and audit["artifact_audit"]["passed"]
            and audit["receipt_audit"]["passed"]
            and audit["build_session_audit"]["passed"]
            and audit["process_argv_audit"]["passed"]
        ):
            audit["status"] = audit["agent_declared_result"] or "INCONCLUSIVE"
    except (IsolationError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        audit["error"] = type(error).__name__
        audit["error_detail"] = str(error).replace(api_key, "<redacted>")
    finally:
        if gateway is not None:
            gateway.terminate()
            gateway.wait(timeout=10)
            if gateway.stderr and (detail := gateway.stderr.read().replace(api_key, "<redacted>").strip()):
                audit["gateway_stderr"] = detail
        shutil.rmtree(codex_home, ignore_errors=True)
        audit["temporary_codex_home_deleted"] = not codex_home.exists()
        audit["finished_at"] = utc_now()
        audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if not args.prepare_only:
            append_execution_log(args.run_tag, str(audit["status"]), audit)
    print(json.dumps({"run_tag": args.run_tag, "status": audit["status"], "audit": str(audit_path)}, ensure_ascii=False))
    return 0 if audit["status"] in {"DEVELOPMENT_READY", "BLOCKED", "PREPARED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
