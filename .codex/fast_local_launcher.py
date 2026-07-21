#!/usr/bin/env python3
"""Prepare and optionally launch a local two-session Claude modeling experiment."""

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
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = "workspaces/ontology-harness/fast-local.json"
DEFAULT_SCENARIO = ".claude/scenarios/dify-foundations-v1.json"
DEFAULT_API_BASE_URL = "http://127.0.0.1:8001/api"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")
SECRET_VALUE_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{16,}={0,2}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|password|secret)\b"
        r"\s*[:=]\s*[^\s,'\"]{12,}"
    ),
)
SECRET_KEY_PARTS = ("api_key", "token", "password", "secret", "authorization", "cookie")


class LauncherError(RuntimeError):
    """Bounded operator-facing launcher failure."""


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LauncherError(f"cannot read JSON object: {path}") from exc
    if not isinstance(value, dict):
        raise LauncherError(f"expected JSON object: {path}")
    return value


def repo_path(
    repo: Path,
    value: str,
    label: str,
    *,
    expected_kind: str = "file",
) -> Path:
    target = (repo / value).resolve()
    try:
        target.relative_to(repo.resolve())
    except ValueError as exc:
        raise LauncherError(f"{label} must be inside the repository") from exc
    if expected_kind == "file" and not target.is_file():
        raise LauncherError(f"{label} does not exist")
    if expected_kind == "directory" and not target.is_dir():
        raise LauncherError(f"{label} directory does not exist")
    if expected_kind == "any" and not target.exists():
        raise LauncherError(f"{label} does not exist")
    if expected_kind not in {"file", "directory", "any"}:
        raise ValueError("invalid expected_kind")
    return target


def contains_secret_material(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if any(part in normalized for part in SECRET_KEY_PARTS):
                return True
            if contains_secret_material(child):
                return True
    elif isinstance(value, list):
        return any(contains_secret_material(child) for child in value)
    elif isinstance(value, str):
        return any(pattern.search(value) for pattern in SECRET_VALUE_PATTERNS)
    return False


def load_scenario(repo: Path, relative: str) -> tuple[Path, dict[str, Any], str]:
    path = repo_path(repo, relative, "scenario")
    scenario = read_object(path)
    required = {
        "schema_version",
        "scenario_id",
        "version",
        "goal",
        "corpus",
        "constraints",
        "simulated_user",
        "acceptance_questions",
    }
    if set(scenario) != required:
        raise LauncherError("scenario fields do not match the version-1 contract")
    if scenario["schema_version"] != 1:
        raise LauncherError("unsupported scenario schema_version")
    for name in ("scenario_id", "version", "goal"):
        if not isinstance(scenario[name], str) or not scenario[name].strip():
            raise LauncherError(f"scenario {name} must be a non-empty string")
    corpus = scenario["corpus"]
    if not isinstance(corpus, dict) or set(corpus) != {"snapshot_id", "path"}:
        raise LauncherError("scenario corpus is invalid")
    if not all(isinstance(corpus[name], str) and corpus[name] for name in corpus):
        raise LauncherError("scenario corpus values are invalid")
    corpus_path = repo_path(repo, corpus["path"], "scenario corpus", expected_kind="any")
    if not corpus_path.is_dir() and not corpus_path.is_file():
        raise LauncherError("scenario corpus does not exist")
    for name in ("constraints", "acceptance_questions"):
        values = scenario[name]
        if (
            not isinstance(values, list)
            or not values
            or not all(isinstance(item, str) and item.strip() for item in values)
        ):
            raise LauncherError(f"scenario {name} must be a non-empty string list")
    simulated = scenario["simulated_user"]
    if (
        not isinstance(simulated, dict)
        or set(simulated) != {"facts", "decision_policy"}
        or not isinstance(simulated["facts"], list)
        or not simulated["facts"]
        or not all(isinstance(item, str) and item.strip() for item in simulated["facts"])
        or not isinstance(simulated["decision_policy"], str)
        or not simulated["decision_policy"].strip()
    ):
        raise LauncherError("scenario simulated_user contract is invalid")
    if contains_secret_material(scenario):
        raise LauncherError("scenario contains secret-like material")
    return path, scenario, hashlib.sha256(path.read_bytes()).hexdigest()


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise LauncherError("credential env file is unavailable") from exc
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if value and value[0:1] == value[-1:] and value.startswith(("'", '"')):
            value = value[1:-1]
        values[name] = value
    return values


def load_config(repo: Path, relative: str) -> tuple[dict[str, Any], str]:
    path = repo_path(repo, relative, "fast-local config")
    config = read_object(path)
    allowed = {
        "schema_version",
        "project_id",
        "api_base_url",
        "api_key",
        "api_key_env_file",
        "api_key_env_name",
        "terminal_executable",
        "claude_executable",
    }
    if set(config) - allowed:
        raise LauncherError("fast-local config has unsupported fields")
    if config.get("schema_version") != 1:
        raise LauncherError("unsupported fast-local config schema_version")
    project_id = config.get("project_id")
    if not isinstance(project_id, str) or not project_id or len(project_id) > 160:
        raise LauncherError("fast-local config project_id is invalid")
    base_url = config.get("api_base_url", DEFAULT_API_BASE_URL)
    parsed = urllib.parse.urlsplit(str(base_url))
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.query
    ):
        raise LauncherError("fast-local config api_base_url is invalid")
    config["api_base_url"] = str(base_url).rstrip("/")
    api_key = config.get("api_key")
    if api_key is None:
        env_file = str(config.get("api_key_env_file", "backend/.env"))
        env_name = str(config.get("api_key_env_name", "ONTOLOGY_MCP_API_KEY"))
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,100}", env_name):
            raise LauncherError("fast-local config api_key_env_name is invalid")
        api_key = parse_env_file(repo_path(repo, env_file, "credential env file")).get(env_name)
    if not isinstance(api_key, str) or not api_key:
        raise LauncherError("configured API key is missing")
    config["api_key"] = api_key
    safe_config = {key: value for key, value in config.items() if key != "api_key"}
    return config, sha256_json(safe_config)


def request_json(
    method: str,
    url: str,
    *,
    api_key: str | None = None,
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    data = canonical(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            status = response.status
    except urllib.error.HTTPError as exc:
        raise LauncherError(f"platform HTTP request failed with status {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise LauncherError("platform HTTP request failed") from exc
    if len(body) > MAX_RESPONSE_BYTES:
        raise LauncherError("platform response exceeds the size boundary")
    try:
        value = json.loads(body or b"{}")
    except json.JSONDecodeError as exc:
        raise LauncherError("platform returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise LauncherError("platform returned a non-object response")
    return status, value


def validate_build_session(body: dict[str, Any], project_id: str) -> dict[str, Any]:
    session = body.get("session", body)
    if not isinstance(session, dict):
        raise LauncherError("platform Build Session response is malformed")
    if session.get("project_id") != project_id:
        raise LauncherError("Build Session belongs to another Project")
    if session.get("status") != "active":
        raise LauncherError("Build Session is not active")
    if not isinstance(session.get("id"), str) or not session["id"]:
        raise LauncherError("platform Build Session response has no id")
    return session


def active_locator_guard(repo: Path, replace: bool, requested_run_id: str | None) -> None:
    locator_path = repo / "workspaces" / "ontology-harness" / "active-run.json"
    if not locator_path.exists():
        return
    locator = read_object(locator_path)
    old_run_id = str(locator.get("run_id", ""))
    if requested_run_id and old_run_id == requested_run_id:
        return
    metadata_path = repo / "workspaces" / "ontology-harness" / old_run_id / "metadata.json"
    non_terminal = False
    if metadata_path.is_file():
        metadata = read_object(metadata_path)
        non_terminal = metadata.get("terminal_state") is None
    if non_terminal and not replace:
        raise LauncherError(
            "active-run locator references a non-terminal run; use --replace-active-locator"
        )


def build_create_payload(run_id: str, scenario: dict[str, Any]) -> dict[str, Any]:
    suffix = hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:16]
    return {
        "client_session_id": f"fast-local-{run_id}",
        "initial_checkpoint": {
            "client_checkpoint_id": f"fast-local-intake-{suffix}",
            "phase": "intake",
            "current_step": "Run the checked-in fast-local modeling scenario",
            "next_step": "Begin evidenced ontology modeling",
            "summary": f"{scenario['scenario_id']} version {scenario['version']}",
            "blockers": [],
        },
    }


def prepare_intent(
    repo: Path,
    *,
    run_id: str,
    project_id: str,
    scenario_relative: str,
    scenario_hash: str,
    config_hash: str,
    scenario: dict[str, Any],
    recovery_build_session_id: str | None,
) -> tuple[Path, dict[str, Any], dict[str, Any] | None]:
    path = repo / "workspaces" / "ontology-harness" / "launch-intents" / f"{run_id}.json"
    existing = read_object(path) if path.exists() else None
    if existing:
        intent_hash = existing.pop("intent_hash", None)
        if not isinstance(intent_hash, str) or intent_hash != sha256_json(existing):
            raise LauncherError("launch intent hash is invalid")
        expected = {
            "run_id": run_id,
            "project_id": project_id,
            "scenario": scenario_relative,
            "scenario_hash": scenario_hash,
            "config_hash": config_hash,
            "recovery_build_session_id": recovery_build_session_id,
        }
        if any(existing.get(key) != value for key, value in expected.items()):
            raise LauncherError("launch intent conflicts with the requested payload")
        payload = existing.get("create_payload")
        if payload is not None and not isinstance(payload, dict):
            raise LauncherError("launch intent create payload is invalid")
        existing["intent_hash"] = intent_hash
        return path, existing, payload

    create_payload = None if recovery_build_session_id else build_create_payload(run_id, scenario)
    intent: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "project_id": project_id,
        "scenario": scenario_relative,
        "scenario_hash": scenario_hash,
        "config_hash": config_hash,
        "client_session_id": create_payload["client_session_id"] if create_payload else None,
        "create_payload": create_payload,
        "create_payload_hash": sha256_json(
            create_payload or {"recovery_build_session_id": recovery_build_session_id}
        ),
        "recovery_build_session_id": recovery_build_session_id,
        "simulated_user_session_id": str(uuid.uuid4()),
        "modeling_agent_session_id": str(uuid.uuid4()),
    }
    intent["intent_hash"] = sha256_json(intent)
    atomic_json(path, intent)
    return path, intent, create_payload


def harness_command(repo: Path, intent: dict[str, Any], build_session_id: str) -> list[str]:
    return [
        sys.executable,
        str(repo / ".codex" / "hooks" / "modeling_harness.py"),
        "prepare-fast",
        "--run-id",
        intent["run_id"],
        "--build-session-id",
        build_session_id,
        "--project-id",
        intent["project_id"],
        "--scenario",
        intent["scenario"],
        "--launch-intent-hash",
        intent["intent_hash"],
        "--simulated-user-session-id",
        intent["simulated_user_session_id"],
        "--modeling-agent-session-id",
        intent["modeling_agent_session_id"],
    ]


def claude_commands(
    repo: Path,
    intent: dict[str, Any],
    build_session_id: str,
    claude_executable: str,
) -> dict[str, list[str]]:
    common = (
        f"Fast-local modeling run {intent['run_id']}; Build Session {build_session_id}; "
        f"scenario {intent['scenario']}. Confirm Harness status once, then begin your assigned role."
    )
    commands: dict[str, list[str]] = {}
    for role, agent, config, prefix in (
        (
            "simulated_user",
            "simulated-user",
            repo / ".claude" / "empty-mcp.json",
            "Read only the scenario and act as the simulated business user. ",
        ),
        (
            "modeling_agent",
            "ontology-modeling-agent",
            repo / ".claude" / "ontology-mcp.json",
            "Use ontology-platform MCP and start evidenced modeling. ",
        ),
    ):
        commands[role] = [
            claude_executable,
            "--agent",
            agent,
            "--session-id",
            intent[f"{role}_session_id"],
            "--dangerously-skip-permissions",
            "--setting-sources=project",
            "--strict-mcp-config",
            f"--mcp-config={config}",
            prefix + common,
        ]
    return commands


def executable(value: str, label: str) -> str:
    resolved = shutil.which(value)
    if not resolved:
        raise LauncherError(f"{label} executable is unavailable")
    return resolved


def _parse_mcp_inventory(value: str) -> tuple[dict[str, str], bool]:
    """Parse only bounded Claude `mcp list` status lines, discarding command details."""
    text = re.sub(r"\x1b\[[0-9;]*m", "", value)
    inventory: dict[str, str] = {}
    no_servers = False
    status_line = re.compile(
        r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}):\s+.*\s+-\s+"
        r"(?P<icon>[✓✔✗✘])\s*(?P<state>[^\r\n]+?)\s*$"
    )
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line == "Checking MCP server health...":
            continue
        if line in {
            "No MCP servers configured",
            "No MCP servers configured.",
            "No MCP servers configured. Use `claude mcp add` to add a server.",
        }:
            if no_servers:
                raise LauncherError("Claude MCP inventory output is ambiguous")
            no_servers = True
            continue
        match = status_line.fullmatch(line)
        if not match:
            raise LauncherError("Claude MCP inventory output is ambiguous")
        name = match.group("name")
        if name in inventory:
            raise LauncherError("Claude MCP inventory contains a duplicate server")
        icon = match.group("icon")
        state_text = re.sub(r"\s+", " ", match.group("state").strip().lower())
        if icon in {"✓", "✔"} and state_text == "connected":
            state = "connected"
        elif icon in {"✗", "✘"} and state_text in {
            "failed",
            "failed to connect",
            "connection failed",
            "disconnected",
            "needs authentication",
            "authentication required",
        }:
            state = "unavailable"
        else:
            raise LauncherError("Claude MCP inventory has an unknown server state")
        inventory[name] = state
    if no_servers and inventory:
        raise LauncherError("Claude MCP inventory output is contradictory")
    return inventory, no_servers


def probe_claude_mcp_isolation(repo: Path, claude_executable: str) -> None:
    """Fail before platform writes unless the CLI proves the two MCP inventories."""
    cases = (
        (repo / ".claude" / "ontology-mcp.json", "ontology-platform"),
        (repo / ".claude" / "empty-mcp.json", None),
    )
    for config, expected_server in cases:
        command = [
            claude_executable,
            "--setting-sources=project",
            "--strict-mcp-config",
            f"--mcp-config={config}",
            "mcp",
            "list",
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30,
                check=False,
                start_new_session=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise LauncherError(
                "Claude MCP isolation probe could not run; verify the local Claude installation"
            ) from exc
        inventory, no_servers = _parse_mcp_inventory(completed.stdout + "\n" + completed.stderr)
        if expected_server is None:
            isolated = completed.returncode == 0 and not inventory and no_servers
        else:
            isolated = (
                completed.returncode == 0
                and inventory == {expected_server: "connected"}
                and not no_servers
            )
        if not isolated:
            raise LauncherError(
                "Claude runtime cannot prove fast-local MCP isolation; upgrade to Claude Code "
                "2.1.215 or newer, then retry, or use strict-eval. No platform state was created"
            )


def run(args: argparse.Namespace, repo: Path) -> dict[str, Any]:
    scenario_path, scenario, scenario_hash = load_scenario(repo, args.scenario)
    scenario_relative = scenario_path.relative_to(repo.resolve()).as_posix()
    config, config_hash = load_config(repo, args.config)
    active_locator_guard(repo, args.replace_active_locator, args.run_id)
    claude_executable = executable(str(config.get("claude_executable", "claude")), "Claude")
    probe_claude_mcp_isolation(repo, claude_executable)
    run_id = args.run_id or f"fast-local-{uuid.uuid4().hex[:20]}"
    if not RUN_ID.fullmatch(run_id):
        raise LauncherError("run_id is invalid")

    _, intent, create_payload = prepare_intent(
        repo,
        run_id=run_id,
        project_id=config["project_id"],
        scenario_relative=scenario_relative,
        scenario_hash=scenario_hash,
        config_hash=config_hash,
        scenario=scenario,
        recovery_build_session_id=args.build_session_id,
    )
    base_url = config["api_base_url"]
    request_json("GET", f"{base_url}/health")
    if args.build_session_id:
        _, body = request_json(
            "GET",
            f"{base_url}/build-sessions/{urllib.parse.quote(args.build_session_id, safe='')}",
            api_key=config["api_key"],
        )
    else:
        assert create_payload is not None
        if sha256_json(create_payload) != intent["create_payload_hash"]:
            raise LauncherError("launch intent create payload has changed")
        _, body = request_json(
            "POST",
            f"{base_url}/projects/{urllib.parse.quote(config['project_id'], safe='')}/build-sessions",
            api_key=config["api_key"],
            payload=create_payload,
        )
    session = validate_build_session(body, config["project_id"])
    build_session_id = session["id"]

    try:
        prepared = subprocess.run(
            harness_command(repo, intent, build_session_id),
            cwd=repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise LauncherError(
            f"Harness preparation failed for run {run_id}; "
            f"Build Session {build_session_id} is recoverable"
        ) from exc
    if prepared.returncode != 0:
        raise LauncherError(
            f"Harness preparation failed for run {run_id}; Build Session {build_session_id} is recoverable"
        )
    locator = {
        "schema_version": 1,
        "evaluation_profile": "fast_local",
        "run_id": run_id,
        "project_id": config["project_id"],
        "build_session_id": build_session_id,
        "scenario": scenario_relative,
        "launch_intent_hash": intent["intent_hash"],
        "simulated_user_session_id": intent["simulated_user_session_id"],
        "modeling_agent_session_id": intent["modeling_agent_session_id"],
    }
    atomic_json(repo / "workspaces" / "ontology-harness" / "active-run.json", locator)

    try:
        commands = claude_commands(repo, intent, build_session_id, claude_executable)
        if not args.no_launch:
            terminal = executable(
                str(config.get("terminal_executable", "gnome-terminal")), "terminal"
            )
            for role in ("simulated_user", "modeling_agent"):
                subprocess.Popen(  # noqa: S603 - argv is fixed and never shell interpreted.
                    [terminal, f"--title=ontology-{role}", "--", *commands[role]],
                    cwd=repo,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
    except (LauncherError, OSError) as exc:
        raise LauncherError(
            f"launch failed for run {run_id}; Build Session {build_session_id} is recoverable: {exc}"
        ) from exc
    return {**locator, "launched": not args.no_launch, "commands": commands}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--scenario", default=DEFAULT_SCENARIO)
    parser.add_argument("--run-id")
    parser.add_argument("--build-session-id")
    parser.add_argument("--replace-active-locator", action="store_true")
    parser.add_argument("--no-launch", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        repo = Path(__file__).resolve().parents[1]
        result = run(parse_args(argv or sys.argv[1:]), repo)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (LauncherError, OSError, subprocess.SubprocessError) as exc:
        print(f"fast-local launcher error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
