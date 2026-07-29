#!/usr/bin/env python3
"""Auditable L0 launcher for the isolated ontology-modeling team experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCENARIO_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCENARIO_ROOT.parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
AGENT_INPUT = SCENARIO_ROOT / "agent-input"
MANIFEST_PATH = AGENT_INPUT / "manifest.json"
AGENT_CONFIG = SCENARIO_ROOT / "agent-config"
RUNTIME_ROOT = SCENARIO_ROOT / "runtime" / "runs"
RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,80}$")
NEEDS_ANSWER = "L0_NEEDS_ANSWER\nquestion_id=l0-confirm-modeling-intent"
COMPLETE = "L0_COMPLETE\nsession_reused=true\nrouted_to=modeling_agent"
CODEX_BINARY = Path(os.environ.get("L0_CODEX_BINARY", "/home/yangxiang/.local/bin/codex"))
HOST_CODEX_AUTH = Path(os.environ.get("L0_HOST_CODEX_AUTH", "/home/yangxiang/.codex/auth.json"))
HOST_CODEX_CONFIG = Path(os.environ.get("L0_HOST_CODEX_CONFIG", "/home/yangxiang/.codex/config.toml"))
TIMEOUT_SECONDS = int(os.environ.get("L0_TIMEOUT_SECONDS", "180"))
STRICT_CONFIG_PLACEHOLDER = "strict-parse-placeholder"
FORBIDDEN_HOST_PATHS = (
    str(REPOSITORY_ROOT),
    "/home/yangxiang/.codex",
    str(SCENARIO_ROOT / "tester-only"),
)


class L0Error(RuntimeError):
    """A fail-closed L0 contract error."""


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now() -> str:
    return datetime.now(UTC).isoformat()


def run_dir(run_id: str) -> Path:
    if not RUN_ID_RE.fullmatch(run_id):
        raise L0Error("run_id must be lowercase alphanumeric with hyphens")
    return RUNTIME_ROOT / run_id


def safe_relative(value: str) -> Path:
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise L0Error(f"unsafe manifest path: {value!r}")
    return path


def read_manifest() -> dict[str, Any]:
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise L0Error("agent-input manifest is invalid") from error
    if set(manifest) != {"manifest_version", "files"} or manifest["manifest_version"] != 1:
        raise L0Error("agent-input manifest version or keys drift")
    files = manifest["files"]
    if not isinstance(files, list) or not files:
        raise L0Error("agent-input manifest has no files")
    declared: set[str] = set()
    for item in files:
        if set(item) != {"path", "sha256"} or not isinstance(item["path"], str):
            raise L0Error("agent-input manifest item drift")
        relative = safe_relative(item["path"])
        if relative.as_posix() in declared or not re.fullmatch(r"[0-9a-f]{64}", str(item["sha256"])):
            raise L0Error("agent-input manifest has duplicate or invalid hash")
        declared.add(relative.as_posix())
    actual = {
        path.relative_to(AGENT_INPUT).as_posix()
        for path in AGENT_INPUT.rglob("*")
        if path.is_file() and path != MANIFEST_PATH
    }
    if declared != actual:
        raise L0Error("agent-input file set differs from manifest")
    return manifest


def stage_agent_input(manifest: dict[str, Any], staging: Path) -> dict[str, Any]:
    staging.mkdir(mode=0o700, parents=True, exist_ok=False)
    shutil.copyfile(MANIFEST_PATH, staging / "manifest.json")
    os.chmod(staging / "manifest.json", 0o444)
    hashes: list[dict[str, str]] = []
    for item in manifest["files"]:
        relative = safe_relative(item["path"])
        source = AGENT_INPUT / relative
        if source.is_symlink() or not source.is_file() or sha256(source) != item["sha256"]:
            raise L0Error(f"agent-input hash or file safety failure: {relative}")
        target = staging / relative
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        os.chmod(target, 0o444)
        if sha256(target) != item["sha256"]:
            raise L0Error(f"staged hash differs: {relative}")
        hashes.append({"path": relative.as_posix(), "sha256": item["sha256"]})
    expected = {"manifest.json", *(item["path"] for item in manifest["files"])}
    actual = {path.relative_to(staging).as_posix() for path in staging.rglob("*") if path.is_file()}
    if actual != expected:
        raise L0Error("staging membership drift")
    return {"manifest_sha256": sha256(MANIFEST_PATH), "files": hashes}


def load_host_key() -> str:
    """Resolve only the configured MCP principal, never the backend bootstrap credential."""
    try:
        config = tomllib.loads(HOST_CODEX_CONFIG.read_text(encoding="utf-8"))
        value = config["mcp_servers"]["ontology_platform"]["env"]["ONTOLOGY_MCP_API_KEY"]
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as error:
        raise L0Error("host Codex ontology_platform MCP key is unavailable") from error
    if not isinstance(value, str) or not value:
        raise L0Error("host Codex ontology_platform MCP key is empty")
    return value


def create_temporary_read_key(run_id: str) -> tuple[str, dict[str, str]]:
    """Create a unique same-project read key; its plaintext never enters audit material."""
    sys.path.insert(0, str(BACKEND_ROOT))
    from app.core.config import Settings  # noqa: PLC0415
    from app.repositories.postgres import create_session_factory  # noqa: PLC0415
    from app.repositories.models import ApiKeyModel  # noqa: PLC0415
    from app.security.auth import create_api_key, resolve_api_key  # noqa: PLC0415

    settings = Settings(_env_file=BACKEND_ROOT / ".env")
    factory = create_session_factory(settings)
    with factory() as session:
        principal = resolve_api_key(session, load_host_key())
        if principal is None or principal.project_id is None:
            raise L0Error("host MCP principal must be project-scoped for L0 temporary key creation")
        record, plaintext = create_api_key(
            session,
            name=f"r2-2-001-l0-{run_id}",
            project_id=principal.project_id,
            scopes=["read"],
        )
        # Confirm the durable record cannot gain model/admin scope silently.
        stored = session.get(ApiKeyModel, record.id)
        if stored is None or stored.project_id != principal.project_id or stored.scopes != ["read"]:
            raise L0Error("temporary API key scope contract was not persisted")
    return plaintext, {"key_id": record.id, "project_id": principal.project_id, "scopes": "read"}


def revoke_temporary_key(key_id: str) -> bool:
    sys.path.insert(0, str(BACKEND_ROOT))
    from app.core.config import Settings  # noqa: PLC0415
    from app.repositories.postgres import create_session_factory  # noqa: PLC0415
    from app.repositories.models import ApiKeyModel  # noqa: PLC0415
    from app.security.auth import revoke_key  # noqa: PLC0415

    with create_session_factory(Settings(_env_file=BACKEND_ROOT / ".env"))() as session:
        record = session.get(ApiKeyModel, key_id)
        if record is None:
            return False
        revoke_key(session, record)
        return record.revoked_at is not None


def write_run_configuration(codex_home: Path, temporary_key: str) -> None:
    """Create role files without MCPs and one run-local root MCP configuration."""
    agents = codex_home / "agents"
    agents.mkdir(mode=0o700, exist_ok=True)
    for name in ("modeling-agent.toml", "platform-protocol-agent.toml"):
        source = AGENT_CONFIG / name
        target = agents / name.replace("-", "_")
        shutil.copyfile(source, target)
        os.chmod(target, 0o600)
    config = (
        "[features]\nmulti_agent = true\n"
        "[projects.\"/work\"]\ntrust_level = \"trusted\"\n"
        "[mcp_servers.ontology_platform]\n"
        "command = \"/uv\"\n"
        "args = [\"run\", \"--directory\", \"/backend\", \"--no-sync\", \"python\", \"-m\", \"app.mcp.server\"]\n"
        "required = true\n"
        "default_tools_approval_mode = \"approve\"\n"
        "startup_timeout_sec = 20.0\n"
        "tool_timeout_sec = 60.0\n"
        "enabled_tools = [\"check_platform_health\"]\n"
        "[mcp_servers.ontology_platform.env]\n"
        f"ONTOLOGY_MCP_API_KEY = {json.dumps(temporary_key)}\n"
    )
    (codex_home / "config.toml").write_text(config, encoding="utf-8")
    os.chmod(codex_home / "config.toml", 0o600)


def bwrap_command(paths: dict[str, Path], command: list[str]) -> list[str]:
    bwrap = ["bwrap", "--die-with-parent", "--new-session", "--share-net", "--clearenv"]
    for source in ("/usr", "/bin", "/lib", "/lib64", "/etc/ssl", "/etc/hosts", "/etc/resolv.conf"):
        if Path(source).exists():
            bwrap.extend(["--ro-bind", source, source])
    uv_binary = Path(shutil.which("uv") or "/home/yangxiang/.local/bin/uv")
    if not uv_binary.is_file():
        raise L0Error("uv executable is unavailable for platform protocol MCP")
    backend_python = (BACKEND_ROOT / ".venv" / "bin" / "python").resolve()
    runtime_root = backend_python.parent.parent
    if not backend_python.is_file() or not runtime_root.is_dir():
        raise L0Error("backend virtualenv interpreter is unavailable for platform protocol MCP")
    runtime_parent = Path("/")
    for part in runtime_root.parts[1:-1]:
        runtime_parent /= part
        bwrap.extend(["--dir", str(runtime_parent)])
    bwrap.extend(
        [
            "--ro-bind", str(CODEX_BINARY.resolve()), "/codex",
            "--ro-bind", str(uv_binary.resolve()), "/uv",
            "--ro-bind", str(BACKEND_ROOT), "/backend",
            "--ro-bind", str(runtime_root), str(runtime_root),
            "--ro-bind", str(paths["staging"]), "/opt",
            "--bind", str(paths["work"]), "/work",
            "--bind", str(paths["codex_home"]), "/codex-home",
            "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
            "--setenv", "PATH", "/usr/bin:/bin",
            "--setenv", "HOME", "/tmp",
            "--setenv", "CODEX_HOME", "/codex-home",
            "--setenv", "NO_PROXY", "127.0.0.1,localhost",
        ]
    )
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        if os.environ.get(name):
            bwrap.extend(["--setenv", name, os.environ[name]])
    return [*bwrap, "--", *command]


def run_isolation_probe(paths: dict[str, Path]) -> dict[str, Any]:
    command = bwrap_command(
        paths,
        [
            "/bin/sh", "-c",
            "test -r /opt/manifest.json && test ! -w /opt && test -w /work && "
            "test ! -e /home/yangxiang/projects/ontology-platform && test ! -e /home/yangxiang/.codex && "
            "test ! -e /opt/isolation-sentinel.txt",
        ],
    )
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    return {"passed": result.returncode == 0, "exit_code": result.returncode, "stderr": result.stderr.strip()}


def strict_config_command() -> list[str]:
    return ["/codex", "--strict-config", "doctor", "--json"]


def verify_strict_config(paths: dict[str, Path]) -> dict[str, Any]:
    """Fail closed unless Codex strictly parses the isolated root configuration."""
    try:
        result = subprocess.run(
            bwrap_command(paths, strict_config_command()),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        report = json.loads(result.stdout)
        config = report["checks"]["config.load"]
        passed = (
            result.returncode == 0
            and config.get("status") == "ok"
            and config.get("details", {}).get("config.toml parse") == "ok"
        )
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, KeyError, TypeError) as error:
        raise L0Error("run-local Codex configuration strict parse failed") from error
    evidence = {"passed": passed, "exit_code": result.returncode, "config_status": config.get("status")}
    if not passed:
        raise L0Error("run-local Codex configuration strict parse failed")
    return evidence


def codex_command(session_id: str | None = None) -> list[str]:
    base = ["/codex", "--ask-for-approval", "never", "exec"]
    if session_id is not None:
        return [
            *base,
            "resume",
            "--json",
            "--skip-git-repo-check",
            "--ignore-rules",
            "--disable",
            "apps",
            "--disable",
            "browser_use",
            "--disable",
            "plugins",
            "--disable",
            "memories",
            session_id,
            "-",
        ]
    return [
        *base,
        "--json",
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write",
        "--ignore-rules",
        "--disable",
        "apps",
        "--disable",
        "browser_use",
        "--disable",
        "plugins",
        "--disable",
        "memories",
        "-C",
        "/work",
        "-",
    ]


def execute(paths: dict[str, Path], prompt: str, transcript: Path, session_id: str | None = None) -> dict[str, Any]:
    started = time.monotonic()
    command = bwrap_command(paths, codex_command(session_id))
    try:
        result = subprocess.run(
            command, input=prompt, text=True, capture_output=True, timeout=TIMEOUT_SECONDS, check=False
        )
        transcript.write_text(result.stdout, encoding="utf-8")
        (transcript.with_suffix(".stderr.log")).write_text(result.stderr, encoding="utf-8")
        return {"exit_code": result.returncode, "elapsed_seconds": round(time.monotonic() - started, 3), "timeout": False}
    except subprocess.TimeoutExpired as error:
        transcript.write_text(error.stdout or "", encoding="utf-8")
        (transcript.with_suffix(".stderr.log")).write_text(error.stderr or "", encoding="utf-8")
        return {"exit_code": None, "elapsed_seconds": round(time.monotonic() - started, 3), "timeout": True}


def jsonl_items(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, json.JSONDecodeError) as error:
        raise L0Error(f"invalid JSONL evidence: {path.name}") from error


def thread_id(items: list[dict[str, Any]]) -> str:
    ids = [
        str(item["thread_id"])
        for item in items
        if item.get("type") == "thread.started" and item.get("thread_id")
    ]
    ids.extend(
        str(item["payload"]["id"])
        for item in items
        if item.get("type") == "session_meta"
        and isinstance(item.get("payload"), dict)
        and item["payload"].get("id")
    )
    if len(set(ids)) != 1:
        raise L0Error("transcript must contain exactly one thread.started ID")
    return ids[0]


def _all_strings(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def marker_count(items: list[dict[str, Any]], marker: str) -> int:
    """Count protocol markers after JSONL decoding, not in escaped source text."""
    def strings(value: object) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            return [text for child in value.values() for text in strings(child)]
        if isinstance(value, list):
            return [text for child in value for text in strings(child)]
        return []

    return sum(marker in text for item in items for text in strings(item))


def spawn_contracts(items: list[dict[str, Any]]) -> dict[str, str]:
    roles: dict[str, str] = {}
    pending: dict[str, str] = {}
    for event in items:
        item = event.get("item", {})
        payload = event.get("payload", {})
        if isinstance(item, dict) and item.get("type") == "collab_tool_call" and item.get("tool") == "spawn_agent":
            text = _all_strings(item)
            call_id = None
            children = item.get("receiver_thread_ids", [])
        elif (
            event.get("type") == "response_item"
            and isinstance(payload, dict)
            and payload.get("type") == "function_call"
            and payload.get("name") == "spawn_agent"
        ):
            text = str(payload.get("arguments", ""))
            call_id = payload.get("call_id")
            children = []
        else:
            continue
        for role in ("modeling_agent", "platform_protocol_agent"):
            normalized = text.replace(" ", "")
            if role in text and ('"fork_turns":"none"' in normalized):
                if isinstance(children, list) and len(children) == 1 and isinstance(children[0], str):
                    if role in roles or children[0] in roles.values():
                        raise L0Error("duplicate role or child rollout ID")
                    roles[role] = children[0]
                elif isinstance(call_id, str):
                    if role in pending:
                        raise L0Error("duplicate role spawn")
                    pending[role] = call_id
    for event in items:
        payload = event.get("payload", {})
        if not (
            event.get("type") == "event_msg"
            and isinstance(payload, dict)
            and payload.get("type") == "sub_agent_activity"
        ):
            continue
        for role, call_id in pending.items():
            if payload.get("event_id") == call_id and isinstance(payload.get("agent_thread_id"), str):
                child_id = payload["agent_thread_id"]
                if role in roles or child_id in roles.values():
                    raise L0Error("duplicate role or child rollout ID")
                roles[role] = child_id
    if set(roles) != {"modeling_agent", "platform_protocol_agent"}:
        raise L0Error("missing explicit role spawn with fork_turns=none")
    return roles


def find_child_rollout(codex_home: Path, child_id: str) -> Path:
    candidates: list[Path] = []
    for path in codex_home.rglob("*.jsonl"):
        try:
            if thread_id(jsonl_items(path)) == child_id:
                candidates.append(path)
        except L0Error:
            continue
    if len(candidates) != 1:
        raise L0Error(f"child rollout is missing or ambiguous: {child_id}")
    return candidates[0]


def mcp_tool_calls(rollout: Path) -> list[str]:
    """Return only executable MCP calls, never prompt mentions or model summaries."""
    calls: list[str] = []
    for event in jsonl_items(rollout):
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            continue
        if (
            payload.get("type") == "function_call"
            and payload.get("namespace") == "mcp__ontology_platform"
        ):
            calls.append(
                "check_platform_health"
                if payload.get("name") == "check_platform_health"
                else "other_ontology_platform_tool"
            )
            continue
        if payload.get("type") != "custom_tool_call":
            continue
        raw_input = str(payload.get("input", ""))
        if "ontology_platform" in raw_input and "check_platform_health" in raw_input:
            calls.append("check_platform_health")
        elif "ontology_platform" in raw_input:
            calls.append("other_ontology_platform_tool")
    return calls


def mcp_call_failures(rollout: Path) -> list[str]:
    """Return MCP error payloads for the allowed platform health tool."""
    failures: list[str] = []
    for event in jsonl_items(rollout):
        payload = event.get("payload", {})
        if not isinstance(payload, dict) or payload.get("type") != "mcp_tool_call_end":
            continue
        invocation = payload.get("invocation", {})
        result = payload.get("result", {})
        if (
            isinstance(invocation, dict)
            and invocation.get("server") == "ontology_platform"
            and invocation.get("tool") == "check_platform_health"
            and isinstance(result, dict)
            and result.get("Err")
        ):
            failures.append(str(result["Err"]))
    return failures


def role_has_fork_contract(coordinator_rollout: Path, role: str) -> bool:
    for event in jsonl_items(coordinator_rollout):
        payload = event.get("payload", {})
        if not (
            event.get("type") == "response_item"
            and isinstance(payload, dict)
            and payload.get("type") == "function_call"
            and payload.get("name") == "spawn_agent"
        ):
            continue
        try:
            arguments = json.loads(str(payload.get("arguments", "")))
        except json.JSONDecodeError:
            continue
        if arguments.get("agent_type") == role and arguments.get("fork_turns") == "none":
            return True
    return False


def audit_children(codex_home: Path, roles: dict[str, str], coordinator_rollout: Path) -> dict[str, Any]:
    if mcp_tool_calls(coordinator_rollout):
        raise L0Error("coordinator rollout called ontology platform MCP")
    evidence: dict[str, Any] = {}
    for role, child_id in roles.items():
        rollout = find_child_rollout(codex_home, child_id)
        content = rollout.read_text(encoding="utf-8")
        has_role = role in content
        has_fork = '"fork_turns":"none"' in content.replace(" ", "") or role_has_fork_contract(
            coordinator_rollout, role
        )
        if not has_role or not has_fork:
            raise L0Error(f"child rollout lacks actual role/fork evidence: {role}")
        mcp_calls = mcp_tool_calls(rollout)
        if role == "platform_protocol_agent" and mcp_calls != ["check_platform_health"]:
            raise L0Error("protocol child rollout lacks check_platform_health MCP item")
        if role == "platform_protocol_agent" and mcp_call_failures(rollout):
            raise L0Error("protocol child health MCP did not return a real response")
        if role == "modeling_agent" and mcp_calls:
            raise L0Error("modeling child rollout called platform MCP")
        evidence[role] = {
            "thread_id": child_id,
            "rollout": rollout.relative_to(codex_home).as_posix(),
            "sha256": sha256(rollout),
            "mcp_calls": mcp_calls,
        }
    return evidence


def scan_forbidden(paths: list[Path], secret: str | None = None) -> dict[str, Any]:
    forbidden: list[str] = []
    secret_found = False
    for root in paths:
        for path in ([root] if root.is_file() else root.rglob("*")):
            if not path.is_file():
                continue
            data = path.read_text(encoding="utf-8", errors="replace")
            if any(value in data for value in FORBIDDEN_HOST_PATHS):
                forbidden.append(str(path))
            secret_found = secret_found or bool(secret and secret in data)
    return {"passed": not forbidden and not secret_found, "forbidden_files": forbidden, "secret_found": secret_found}


def write_audit(directory: Path, name: str, payload: dict[str, Any]) -> Path:
    path = directory / "audit" / name
    temporary_path: Path | None = None
    descriptor: int | None = None
    failure: OSError | None = None
    cleanup_failure: OSError | None = None
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{name}.", dir=path.parent)
        temporary_path = Path(temporary_name)
        os.fchmod(descriptor, 0o600)
        data = canonical_json(payload)
        offset = 0
        while offset < len(data):
            written = os.write(descriptor, data[offset:])
            if written <= 0:
                raise OSError("audit temporary write made no progress")
            offset += written
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o400)
        os.close(descriptor)
        descriptor = None
        os.replace(temporary_path, path)
        temporary_path = None
        directory_descriptor = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as error:
        failure = error
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError as error:
                failure = failure or error
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except OSError as error:
                cleanup_failure = error
    if failure is not None:
        if cleanup_failure is not None:
            raise L0Error(f"audit evidence publication failed and temp cleanup failed: {name}") from cleanup_failure
        raise L0Error(f"audit evidence publication failed: {name}") from failure
    if cleanup_failure is not None:
        raise L0Error(f"audit evidence temp cleanup failed: {name}") from cleanup_failure
    return path


def load_state(directory: Path) -> dict[str, Any]:
    try:
        return json.loads((directory / "audit" / "state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise L0Error("run state is missing or invalid") from error


def save_state(directory: Path, state: dict[str, Any]) -> None:
    write_audit(directory, "state.json", state)


def prepare_paths(directory: Path) -> dict[str, Path]:
    return {
        "root": directory,
        "staging": directory / "staging",
        "work": directory / "team-work",
        "codex_home": directory / "temporary-codex-home",
        "transcripts": directory / "transcripts",
    }


def start(run_id: str) -> dict[str, Any]:
    directory = run_dir(run_id)
    if directory.exists():
        raise L0Error("run directory already exists")
    manifest = read_manifest()
    paths = prepare_paths(directory)
    temporary_key: str | None = None
    state: dict[str, Any] = {"run_id": run_id, "state": "INCONCLUSIVE", "started_at": now()}
    try:
        directory.mkdir(mode=0o700, parents=True)
        paths["work"].mkdir(mode=0o700)
        paths["transcripts"].mkdir(mode=0o700)
        stage = stage_agent_input(manifest, paths["staging"])
        paths["codex_home"].mkdir(mode=0o700)
        if not CODEX_BINARY.is_file() or not HOST_CODEX_AUTH.is_file():
            raise L0Error("Codex executable or host authentication is unavailable")
        shutil.copyfile(HOST_CODEX_AUTH, paths["codex_home"] / "auth.json")
        os.chmod(paths["codex_home"] / "auth.json", 0o600)
        write_run_configuration(paths["codex_home"], STRICT_CONFIG_PLACEHOLDER)
        write_audit(directory, "strict-config-pre-key.json", verify_strict_config(paths))
        temporary_key, key_audit = create_temporary_read_key(run_id)
        state["temporary_key"] = key_audit
        write_run_configuration(paths["codex_home"], temporary_key)
        write_audit(directory, "strict-config.json", verify_strict_config(paths))
        probe = run_isolation_probe(paths)
        if not probe["passed"]:
            raise L0Error("bubblewrap isolation probe failed")
        execution = execute(paths, (AGENT_INPUT / "coordinator-task.md").read_text(encoding="utf-8"), paths["transcripts"] / "start.jsonl")
        if execution["timeout"]:
            raise L0Error("Codex start timeout")
        items = jsonl_items(paths["transcripts"] / "start.jsonl")
        coordinator_id = thread_id(items)
        coordinator_rollout = find_child_rollout(paths["codex_home"], coordinator_id)
        roles = spawn_contracts(jsonl_items(coordinator_rollout))
        children = audit_children(paths["codex_home"], roles, coordinator_rollout)
        if marker_count(items, NEEDS_ANSWER) != 1 or execution["exit_code"] != 0:
            raise L0Error("start transcript lacks a unique L0_NEEDS_ANSWER marker")
        child_rollouts = [
            paths["codex_home"] / item["rollout"] for item in children.values()
        ]
        scan = scan_forbidden(
            [paths["transcripts"], directory / "audit", coordinator_rollout, *child_rollouts],
            temporary_key,
        )
        if not scan["passed"]:
            raise L0Error("secret or forbidden host path entered L0 evidence")
        state.update(
            {
                "state": "WAITING_FOR_ANSWER",
                "coordinator_session_id": coordinator_id,
                "temporary_key": key_audit,
                "stage": stage,
                "isolation_probe": probe,
                "start_execution": execution,
                "children": children,
                "coordinator_rollout": coordinator_rollout.relative_to(paths["codex_home"]).as_posix(),
                "updated_at": now(),
            }
        )
        save_state(directory, state)
        return state
    except Exception as error:
        if temporary_key is not None:
            state["key_revoked"] = revoke_temporary_key(state.get("temporary_key", {}).get("key_id", ""))
        state.update({"state": "INCONCLUSIVE", "error": str(error), "updated_at": now()})
        save_state(directory, state)
        raise


def resume(run_id: str, answer: str) -> dict[str, Any]:
    directory = run_dir(run_id)
    state = load_state(directory)
    if state.get("state") != "WAITING_FOR_ANSWER" or not answer:
        raise L0Error("only a waiting run with a non-empty answer can resume")
    paths = prepare_paths(directory)
    try:
        prompt = f"question_id=l0-confirm-modeling-intent\nanswer={answer}"
        execution = execute(paths, prompt, paths["transcripts"] / "resume.jsonl", state["coordinator_session_id"])
        items = jsonl_items(paths["transcripts"] / "resume.jsonl")
        if execution["timeout"] or execution["exit_code"] != 0 or thread_id(items) != state["coordinator_session_id"]:
            raise L0Error("resume did not reuse the coordinator session")
        if marker_count(items, COMPLETE) != 1:
            raise L0Error("resume transcript lacks a unique L0_COMPLETE marker")
        state.update({"state": "COMPLETE", "resume_execution": execution, "answer_sha256": hashlib.sha256(answer.encode()).hexdigest(), "updated_at": now()})
        return state
    finally:
        key_id = state.get("temporary_key", {}).get("key_id")
        state["key_revoked"] = bool(key_id and revoke_temporary_key(key_id))
        save_state(directory, state)


def audit(run_id: str) -> dict[str, Any]:
    directory = run_dir(run_id)
    state = load_state(directory)
    paths = prepare_paths(directory)
    key_id = state.get("temporary_key", {}).get("key_id")
    if state.get("state") not in {"COMPLETE", "FAIL", "INCONCLUSIVE"} or not state.get("key_revoked"):
        raise L0Error("audit requires terminal state with revoked temporary key")
    evidence = {
        "run_id": run_id,
        "state": state["state"],
        "coordinator_session_id": state.get("coordinator_session_id"),
        "temporary_key_id": key_id,
        "temporary_key_scopes": state.get("temporary_key", {}).get("scopes"),
        "children": state.get("children"),
        "start_sha256": sha256(paths["transcripts"] / "start.jsonl"),
        "resume_sha256": sha256(paths["transcripts"] / "resume.jsonl"),
        "generated_at": now(),
    }
    scan = scan_forbidden([paths["transcripts"], directory / "audit"])
    if not scan["passed"]:
        raise L0Error("forbidden host path entered final evidence")
    write_audit(directory, "final-audit.json", evidence)
    return evidence


def cleanup(run_id: str) -> dict[str, Any]:
    directory = run_dir(run_id)
    state = load_state(directory)
    key_id = state.get("temporary_key", {}).get("key_id")
    state["key_revoked"] = bool(key_id and revoke_temporary_key(key_id))
    state["updated_at"] = now()
    save_state(directory, state)
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("start", "audit", "cleanup"):
        child = commands.add_parser(name)
        child.add_argument("--run-id", required=True)
    resume_parser = commands.add_parser("resume")
    resume_parser.add_argument("--run-id", required=True)
    resume_parser.add_argument("--answer", required=True)
    args = parser.parse_args()
    try:
        result = {"start": start, "resume": lambda item: resume(item, args.answer), "audit": audit, "cleanup": cleanup}[args.command](args.run_id)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except L0Error as error:
        print(f"L0 error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
