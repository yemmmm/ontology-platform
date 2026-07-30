#!/usr/bin/env python3
"""Fail-closed L1 launcher for the isolated ontology-modeling-team experiment.

This is deliberately scenario infrastructure: it stages immutable input, starts isolated processes,
and audits receipts. It never generates Modeling Items or selects ontology semantics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib import error, request


SCENARIO_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCENARIO_ROOT.parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
APP_ROOT = BACKEND_ROOT / "app"
AGENT_INPUT = SCENARIO_ROOT / "agent-input"
AGENT_CONFIG = SCENARIO_ROOT / "agent-config"
MANIFEST_PATH = AGENT_INPUT / "manifest.json"
RUNTIME_ROOT = SCENARIO_ROOT / "runtime" / "runs"
SNAPSHOT_SOURCE = (
    REPOSITORY_ROOT
    / "docs/evaluation-corpora/dify-foundations/snapshots/dify-foundations-2026-07-18-5396c1a"
    / "official/en/cloud/use-dify/build/version-control.mdx"
)
RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,80}$")
CODEX_BINARY = Path(os.environ.get("L1_CODEX_BINARY", "/home/yangxiang/.local/bin/codex"))
HOST_CODEX_AUTH = Path(os.environ.get("L1_HOST_CODEX_AUTH", "/home/yangxiang/.codex/auth.json"))
TIMEOUT_SECONDS = int(os.environ.get("L1_TIMEOUT_SECONDS", "300"))
FIRST_RESPONSE_SECONDS = int(os.environ.get("L1_FIRST_RESPONSE_SECONDS", "60"))
HOST_KEY_MARKERS = ("ONTOLOGY_MCP_API_KEY", "sk_admin_", "bootstrap-admin")
PROTOCOL_TOOLS = (
    "check_platform_health",
    "get_modeling_context",
    "create_build_session",
    "get_build_session",
    "acquire_ontology_lease",
    "submit_modeling_batch",
    "get_modeling_batch",
    "get_ontology_read_model",
    "save_build_checkpoint",
    "complete_build_session",
    "cancel_build_session",
)


class L1Error(RuntimeError):
    """A scenario contract condition failed; no semantic fallback is permitted."""


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now() -> str:
    return datetime.now(UTC).isoformat()


def run_dir(run_id: str) -> Path:
    if not RUN_ID_RE.fullmatch(run_id):
        raise L1Error("run_id must be lowercase alphanumeric with hyphens")
    return RUNTIME_ROOT / run_id


def safe_relative(value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise L1Error("manifest path is invalid")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise L1Error("manifest path is unsafe")
    return path


def read_manifest() -> dict[str, Any]:
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise L1Error("L1 input manifest is invalid") from exc
    if set(manifest) != {"manifest_version", "source", "files"} or manifest.get("manifest_version") != 1:
        raise L1Error("L1 input manifest fields drift")
    source = manifest.get("source")
    if not isinstance(source, dict) or set(source) != {"snapshot", "path", "sha256"}:
        raise L1Error("L1 source manifest fields drift")
    if source.get("snapshot") != "dify-foundations-2026-07-18-5396c1a" or source.get("path") != "official/en/cloud/use-dify/build/version-control.mdx":
        raise L1Error("L1 source identity drift")
    if source.get("sha256") != sha256(SNAPSHOT_SOURCE):
        raise L1Error("pinned source hash drift")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise L1Error("L1 manifest has no staged files")
    declared: set[str] = set()
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise L1Error("L1 manifest item fields drift")
        relative = safe_relative(item.get("path"))
        digest = item.get("sha256")
        if relative.as_posix() in declared or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise L1Error("L1 manifest item hash is invalid")
        declared.add(relative.as_posix())
    actual = {
        path.relative_to(AGENT_INPUT).as_posix()
        for path in AGENT_INPUT.rglob("*")
        if path.is_file() and path != MANIFEST_PATH
    }
    if actual != declared:
        raise L1Error("L1 staged input set differs from manifest")
    for item in files:
        path = AGENT_INPUT / safe_relative(item["path"])
        if path.is_symlink() or sha256(path) != item["sha256"]:
            raise L1Error(f"L1 staged input hash drift: {item['path']}")
    if sha256(AGENT_INPUT / "official/version-control.mdx") != source["sha256"]:
        raise L1Error("staged Version Control page does not match the pinned source")
    return manifest


def stage_input(manifest: dict[str, Any], destination: Path, names: set[str] | None = None) -> dict[str, Any]:
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    selected = [item for item in manifest["files"] if names is None or item["path"] in names]
    for item in selected:
        relative = safe_relative(item["path"])
        source, target = AGENT_INPUT / relative, destination / relative
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        os.chmod(target, 0o444)
    staged = {path.relative_to(destination).as_posix() for path in destination.rglob("*") if path.is_file()}
    expected = {item["path"] for item in selected}
    if staged != expected:
        raise L1Error("staged namespace membership drift")
    return {"files": sorted(expected), "sha256": hashlib.sha256(canonical_json(selected)).hexdigest()}


def write_json(path: Path, value: dict[str, Any], *, mode: int = 0o400) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_json(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except OSError as exc:
        Path(temporary).unlink(missing_ok=True)
        raise L1Error(f"audit publication failed: {path.name}") from exc


def paths_for(directory: Path) -> dict[str, Path]:
    return {
        "root": directory,
        "coordinator_input": directory / "coordinator-input",
        "protocol_input": directory / "protocol-input",
        "coordinator_work": directory / "coordinator-work",
        "protocol_work": directory / "protocol-work",
        "coordinator_home": directory / "coordinator-codex-home",
        "protocol_home": directory / "protocol-codex-home",
        "transcripts": directory / "transcripts",
        "audit": directory / "audit",
    }


def _runtime_root() -> Path:
    interpreter = (BACKEND_ROOT / ".venv/bin/python").resolve()
    if not interpreter.is_file():
        raise L1Error("backend virtualenv interpreter is unavailable")
    return interpreter.parent.parent


def _venv_root() -> Path:
    root = BACKEND_ROOT / ".venv"
    if not (root / "bin/python").is_file():
        raise L1Error("backend virtualenv is unavailable")
    return root


def _bwrap_base(paths: dict[str, Path], *, role: str, command: list[str], settings: dict[str, str], include_mcp_home: bool = False) -> list[str]:
    bwrap = ["bwrap", "--die-with-parent", "--new-session", "--share-net", "--clearenv"]
    for source in ("/usr", "/bin", "/lib", "/lib64", "/etc/ssl", "/etc/hosts", "/etc/resolv.conf"):
        if Path(source).exists():
            bwrap.extend(["--ro-bind", source, source])
    if role != "coordinator":
        runtime = _runtime_root()
        for index in range(1, len(runtime.parts) - 1):
            bwrap.extend(["--dir", str(Path("/").joinpath(*runtime.parts[1 : index + 1]))])
        bwrap.extend(["--ro-bind", str(runtime), str(runtime)])
    if role == "coordinator":
        bwrap.extend(["--ro-bind", str(CODEX_BINARY.resolve()), "/codex", "--ro-bind", str(paths["coordinator_input"]), "/opt", "--bind", str(paths["coordinator_work"]), "/work", "--bind", str(paths["coordinator_home"]), "/codex-home"])
    elif role == "protocol":
        bwrap.extend(["--ro-bind", str(CODEX_BINARY.resolve()), "/codex", "--dir", "/backend", "--ro-bind", str(APP_ROOT), "/backend/app", "--ro-bind", str(_venv_root()), "/backend/.venv", "--ro-bind", str(paths["protocol_input"]), "/opt", "--bind", str(paths["protocol_work"]), "/work", "--bind", str(paths["protocol_home"]), "/codex-home"])
    elif role == "rest":
        bwrap.extend(["--dir", "/backend", "--ro-bind", str(APP_ROOT), "/backend/app", "--ro-bind", str(_venv_root()), "/backend/.venv"])
    else:
        raise L1Error("unknown isolated role")
    bwrap.extend(["--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp", "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "HOME", "/tmp", "--setenv", "PYTHONPATH", "/backend", "--setenv", "NO_PROXY", "127.0.0.1,localhost"])
    # The coordinator/modeler namespace has no platform mount or platform configuration. Only the
    # protocol and isolated REST namespace receive database/graph/write-mode settings explicitly.
    role_settings = {} if role == "coordinator" else settings
    for key, value in role_settings.items():
        bwrap.extend(["--setenv", key, value])
    if include_mcp_home:
        bwrap.extend(["--setenv", "CODEX_HOME", "/codex-home"])
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        if os.environ.get(key):
            bwrap.extend(["--setenv", key, os.environ[key]])
    return [*bwrap, "--", *command]


def sanitized_settings() -> dict[str, str]:
    sys.path.insert(0, str(BACKEND_ROOT))
    from app.core.config import Settings  # noqa: PLC0415

    configured = Settings(_env_file=BACKEND_ROOT / ".env")
    values = {
        "DATABASE_URL": configured.database_url,
        "OXIGRAPH_URL": configured.oxigraph_url,
        "SEMANTIC_PRODUCT_WRITE_MODE": "rdf_primary",
        "SEMANTIC_CANONICAL_STORE": configured.semantic_canonical_store,
        "SEMANTIC_READ_MODE": configured.semantic_read_mode,
        "SEMANTIC_LEGACY_WRITE_BLOCKED": str(configured.semantic_legacy_write_blocked).lower(),
        "APP_ENV": configured.app_env,
    }
    return {key: str(value) for key, value in values.items() if value is not None}


def probe_sanitized_configuration(paths: dict[str, Path], settings: dict[str, str]) -> dict[str, Any]:
    command = _bwrap_base(
        paths,
        role="rest",
        settings=settings,
        command=["/backend/.venv/bin/python", "-c", "from app.core.config import Settings; import json; s=Settings(); print(json.dumps({'mode': s.semantic_product_write_mode}))"],
    )
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise L1Error("sanitized configuration probe returned invalid JSON") from exc
    if result.returncode != 0 or payload != {"mode": "rdf_primary"}:
        raise L1Error("sanitized configuration did not resolve rdf_primary")
    return {"passed": True, "mode": payload["mode"], "backend_dotenv_present": False}


def start_isolated_rest(paths: dict[str, Path], settings: dict[str, str], port: int) -> subprocess.Popen[str]:
    command = _bwrap_base(
        paths,
        role="rest",
        settings=settings,
        command=["/backend/.venv/bin/python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
    )
    log = (paths["audit"] / "isolated-rest.log").open("w", encoding="utf-8")
    process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, text=True, start_new_session=True)
    for _ in range(40):
        if process.poll() is not None:
            raise L1Error("isolated REST runtime exited before health")
        try:
            response = http_request(f"http://127.0.0.1:{port}", "GET", "/api/health")
            if response["status"] == 200:
                return process
        except L1Error:
            pass
        time.sleep(0.25)
    stop_process(process)
    raise L1Error("isolated REST runtime did not become healthy")


def stop_process(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)


def http_request(base_url: str, method: str, path: str, body: dict[str, Any] | None = None, key: str | None = None) -> dict[str, Any]:
    payload = canonical_json(body) if body is not None else None
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    call = request.Request(base_url.rstrip("/") + path, data=payload, method=method, headers=headers)
    try:
        with request.urlopen(call, timeout=20) as response:
            raw = response.read()
            return {"status": response.status, "body": json.loads(raw) if raw else {}}
    except error.HTTPError as exc:
        raw = exc.read()
        try:
            body_value = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body_value = {"detail": raw.decode("utf-8", errors="replace")}
        return {"status": exc.code, "body": body_value}
    except OSError as exc:
        raise L1Error(f"HTTP {method} {path} failed") from exc


def require_ok(response: dict[str, Any], expected: set[int] = {200, 201, 204}) -> dict[str, Any]:
    if response.get("status") not in expected or not isinstance(response.get("body"), dict):
        raise L1Error(f"REST request failed: {response.get('status')} {response.get('body')}")
    return response["body"]


def bootstrap_admin() -> tuple[str, dict[str, str]]:
    sys.path.insert(0, str(BACKEND_ROOT))
    from app.core.config import Settings  # noqa: PLC0415
    from app.repositories.postgres import create_session_factory  # noqa: PLC0415
    from app.security.auth import create_api_key  # noqa: PLC0415

    with create_session_factory(Settings(_env_file=BACKEND_ROOT / ".env"))() as session:
        record, plaintext = create_api_key(session, name=f"r2-2-001-l1-host-{int(time.time())}", project_id=None, scopes=["admin"])
    return plaintext, {"key_id": record.id, "scope": "admin", "project_id": ""}


def bootstrap_revoke(key_id: str) -> bool:
    sys.path.insert(0, str(BACKEND_ROOT))
    from app.core.config import Settings  # noqa: PLC0415
    from app.repositories.models import ApiKeyModel  # noqa: PLC0415
    from app.repositories.postgres import create_session_factory  # noqa: PLC0415
    from app.security.auth import revoke_key  # noqa: PLC0415

    with create_session_factory(Settings(_env_file=BACKEND_ROOT / ".env"))() as session:
        record = session.get(ApiKeyModel, key_id)
        if record is None:
            return False
        return revoke_key(session, record).revoked_at is not None


def choose_port(run_id: str) -> int:
    return 18000 + int(hashlib.sha256(run_id.encode()).hexdigest()[:4], 16) % 1000


def write_coordinator_config(home: Path) -> None:
    home.mkdir(mode=0o700)
    shutil.copyfile(HOST_CODEX_AUTH, home / "auth.json")
    os.chmod(home / "auth.json", 0o600)
    agents = home / "agents"
    agents.mkdir(mode=0o700)
    for source in AGENT_CONFIG.glob("*.toml"):
        shutil.copyfile(source, agents / source.name.replace("-", "_"))
    (home / "config.toml").write_text("[features]\nmulti_agent = true\n[projects.\"/work\"]\ntrust_level = \"trusted\"\n", encoding="utf-8")
    os.chmod(home / "config.toml", 0o600)


def write_protocol_config(home: Path, model_key: str, settings: dict[str, str]) -> None:
    home.mkdir(mode=0o700)
    shutil.copyfile(HOST_CODEX_AUTH, home / "auth.json")
    os.chmod(home / "auth.json", 0o600)
    enabled = ", ".join(json.dumps(tool) for tool in PROTOCOL_TOOLS)
    env = {**settings, "ONTOLOGY_MCP_API_KEY": model_key}
    text = ["[projects.\"/work\"]", 'trust_level = "trusted"', "[mcp_servers.ontology_platform]", 'command = "/backend/.venv/bin/python"', 'args = ["-m", "app.mcp.server"]', 'cwd = "/backend"', 'default_tools_approval_mode = "approve"', "required = true", "startup_timeout_sec = 20.0", "tool_timeout_sec = 90.0", f"enabled_tools = [{enabled}]", "[mcp_servers.ontology_platform.env]"]
    text.extend(f"{key} = {json.dumps(value)}" for key, value in sorted(env.items()))
    (home / "config.toml").write_text("\n".join(text) + "\n", encoding="utf-8")
    os.chmod(home / "config.toml", 0o600)


def verify_strict_config(paths: dict[str, Path], role: str, settings: dict[str, str]) -> None:
    command = _bwrap_base(
        paths,
        role=role,
        command=["/codex", "--strict-config", "doctor", "--json"],
        settings=settings,
        include_mcp_home=True,
    )
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    try:
        report = json.loads(result.stdout)
        status = report["checks"]["config.load"]["status"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise L1Error(f"{role} Codex strict configuration probe failed") from exc
    if result.returncode != 0 or status != "ok":
        raise L1Error(f"{role} Codex strict configuration is invalid")


def probe_mcp_requires_run_key(paths: dict[str, Path], settings: dict[str, str]) -> None:
    """Start the exact sanitized stdio MCP command with no run key; it must fail before serving."""
    command = _bwrap_base(
        paths,
        role="rest",
        settings=settings,
        command=["/backend/.venv/bin/python", "-m", "app.mcp.server"],
    )
    result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    if result.returncode == 0 or "ONTOLOGY_MCP_API_KEY is required" not in result.stderr:
        raise L1Error("sanitized MCP without the run key did not reject authentication")


def codex_command(session_id: str | None = None) -> list[str]:
    if session_id:
        return ["/codex", "--ask-for-approval", "never", "exec", "resume", "--json", "--skip-git-repo-check", "--ignore-rules", "--disable", "apps", "--disable", "browser_use", "--disable", "plugins", "--disable", "memories", session_id, "-"]
    return ["/codex", "--ask-for-approval", "never", "exec", "--json", "--skip-git-repo-check", "--sandbox", "workspace-write", "--ignore-rules", "--disable", "apps", "--disable", "browser_use", "--disable", "plugins", "--disable", "memories", "-C", "/work", "-"]


def _thread_id(transcript: Path) -> str:
    ids: set[str] = set()
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "thread.started" and isinstance(event.get("thread_id"), str):
            ids.add(event["thread_id"])
        payload = event.get("payload")
        if event.get("type") == "session_meta" and isinstance(payload, dict) and isinstance(payload.get("id"), str):
            ids.add(payload["id"])
    if len(ids) != 1:
        raise L1Error("Codex transcript lacks one exact coordinator thread ID")
    return ids.pop()


def execute_agent(paths: dict[str, Path], role: str, prompt: str, transcript: Path, settings: dict[str, str], session_id: str | None = None) -> dict[str, Any]:
    command = _bwrap_base(paths, role=role, command=codex_command(session_id), settings=settings, include_mcp_home=True)
    started = time.monotonic()
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, start_new_session=True)
    assert process.stdin and process.stdout and process.stderr
    process.stdin.write(prompt)
    process.stdin.close()
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    first_seen = False
    terminal_error: str | None = None
    with transcript.open("w", encoding="utf-8") as out, transcript.with_suffix(".stderr.log").open("w", encoding="utf-8") as err:
        while process.poll() is None:
            elapsed = time.monotonic() - started
            if (not first_seen and elapsed > FIRST_RESPONSE_SECONDS) or elapsed > TIMEOUT_SECONDS:
                terminal_error = "first_response_timeout" if not first_seen else "terminal_timeout"
                os.killpg(process.pid, signal.SIGTERM)
                break
            for key, _ in selector.select(timeout=0.5):
                line = key.fileobj.readline()
                if not line:
                    continue
                (out if key.data == "stdout" else err).write(line)
                (out if key.data == "stdout" else err).flush()
                if key.data == "stdout":
                    first_seen = True
                    if any(marker in line.lower() for marker in ("provider error", "agent terminal error", "fatal error")):
                        terminal_error = "agent_terminal_error"
                        os.killpg(process.pid, signal.SIGTERM)
                        break
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
        # Do not discard a final buffered event merely because the child exited between polls.
        for stream, target in ((process.stdout, out), (process.stderr, err)):
            remainder = stream.read()
            if remainder:
                target.write(remainder)
                target.flush()
            stream.close()
    selector.close()
    if terminal_error:
        raise L1Error(f"{role} runtime/infrastructure: {terminal_error}")
    if process.returncode != 0:
        raise L1Error(f"{role} runtime/infrastructure: exit_{process.returncode}")
    return {"exit_code": process.returncode, "elapsed_seconds": round(time.monotonic() - started, 3), "thread_id": _thread_id(transcript)}


def _candidate_and_dispatch(work: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        candidate = json.loads((work / "approved-candidate.json").read_text(encoding="utf-8"))
        dispatch = json.loads((work / "protocol-dispatch.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise L1Error("coordinator did not publish candidate and dispatch") from exc
    if not isinstance(candidate, dict) or set(candidate) != {"business_question", "synthetic_workflow", "concepts", "states", "minimum_constraint"}:
        raise L1Error("coordinator candidate contract drift")
    forbidden = ("item", "batch", "key", "receipt", "query", "m1", "m2", "m3", "m4", "m5", "m6")
    if any(word in canonical_json(candidate).decode("utf-8").lower() for word in forbidden):
        raise L1Error("coordinator candidate leaks protocol or hidden answer material")
    expected = {"task_id", "candidate_sha256", "requested_outcome"}
    if not isinstance(dispatch, dict) or set(dispatch) != expected or dispatch.get("requested_outcome") != "apply_version_state":
        raise L1Error("coordinator dispatch contract drift")
    # The coordinator authorizes the task and requested outcome. Canonical JSON/hash generation is
    # deterministic launcher protocol work, so a model-written hash is never trusted or retried.
    normalized = {**dispatch, "candidate_sha256": hashlib.sha256(canonical_json(candidate)).hexdigest()}
    return candidate, normalized


def scan_forbidden(paths: list[Path], secret: str | None = None) -> dict[str, Any]:
    forbidden_files: list[str] = []
    for root in paths:
        for path in ([root] if root.is_file() else root.rglob("*")):
            if not path.is_file():
                continue
            data = path.read_text(encoding="utf-8", errors="replace")
            if str(REPOSITORY_ROOT) in data or any(marker in data for marker in HOST_KEY_MARKERS) or (secret and secret in data):
                forbidden_files.append(str(path))
    return {"passed": not forbidden_files, "forbidden_files": forbidden_files}


def _key_record_revoked(key_id: str) -> bool:
    sys.path.insert(0, str(BACKEND_ROOT))
    from app.core.config import Settings  # noqa: PLC0415
    from app.repositories.models import ApiKeyModel  # noqa: PLC0415
    from app.repositories.postgres import create_session_factory  # noqa: PLC0415

    with create_session_factory(Settings(_env_file=BACKEND_ROOT / ".env"))() as session:
        record = session.get(ApiKeyModel, key_id)
        return record is not None and record.revoked_at is not None


def validate_protocol_result(value: object) -> dict[str, Any]:
    """Validate normalized, credential-free receipts without interpreting ontology semantics."""
    if not isinstance(value, dict):
        raise L1Error("protocol result is not an object")
    required = {"build_session_id", "structural", "negative_dry_run", "workspace", "read_model"}
    if set(value) != required or not isinstance(value.get("build_session_id"), str):
        raise L1Error("protocol result fields drift")
    workspace = value.get("workspace")
    if not isinstance(workspace, dict) or set(workspace) != {"before", "after"} or workspace["before"] == workspace["after"]:
        raise L1Error("protocol result does not prove workspace advancement")
    for name in ("structural",):
        transition = value.get(name)
        if not isinstance(transition, dict) or set(transition) != {"dry_run", "apply"}:
            raise L1Error(f"protocol {name} transition fields drift")
        dry, applied = transition["dry_run"], transition["apply"]
        if not isinstance(dry, dict) or not isinstance(applied, dict):
            raise L1Error(f"protocol {name} transition receipt is invalid")
        if dry.get("attempt_status") != "validated" or applied.get("attempt_status") != "applied":
            raise L1Error(f"protocol {name} dry-run/apply status drift")
        stable = ("batch_id", "client_batch_id", "items_sha256")
        if any(not isinstance(dry.get(key), str) or dry.get(key) != applied.get(key) for key in stable):
            raise L1Error(f"protocol {name} dry-run/apply candidate drift")
    invalid = value.get("negative_dry_run")
    if not isinstance(invalid, dict) or not isinstance(invalid.get("batch_id"), str) or invalid.get("attempt_status") != "validation_failed" or invalid.get("applied") is not False:
        raise L1Error("negative candidate was not rejected as dry-run only")
    read_model = value.get("read_model")
    if not isinstance(read_model, dict) or read_model.get("generic") is not True or read_model.get("draft_latest_distinct") is not True:
        raise L1Error("generic read did not prove the required draft/latest distinction")
    if any(marker in canonical_json(value).decode("utf-8") for marker in HOST_KEY_MARKERS):
        raise L1Error("protocol result contains credential material")
    return value


def audit_s0(paths: dict[str, Path]) -> dict[str, Any]:
    """Fail closed: S0 is complete before any platform runtime or credential exists."""
    transcript = paths["transcripts"] / "s0.jsonl"
    result = json.loads((paths["coordinator_work"] / "s0-result.json").read_text(encoding="utf-8"))
    if not isinstance(result, dict) or result.get("no_platform_write") is not True:
        raise L1Error("S0 did not publish no-write evidence")
    rollouts = sorted((paths["coordinator_home"] / "sessions").rglob("*.jsonl"))
    # One parent and exactly two independently launched children is the observable evidence for the
    # S0 modeling_agent/protocol_planning_agent split. Names are config-only and not emitted by CLI JSONL.
    if len(rollouts) != 3 or len({_thread_id(rollout) for rollout in rollouts}) != 3:
        raise L1Error("S0 lacks two distinct isolated child rollout identities")
    if any(_contains_mcp_call(rollout) for rollout in [transcript, *rollouts]):
        raise L1Error("S0 invoked platform MCP")
    return {"no_platform_write": True, "thread_id": _thread_id(transcript), "child_rollout_count": 2}


def _contains_mcp_call(transcript: Path) -> bool:
    """Check the Codex JSONL event stream, rather than an Agent-authored receipt."""
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        encoded = canonical_json(event).decode("utf-8").lower()
        if "mcp_tool_call" in encoded or "ontology_platform" in encoded:
            return True
    return False


def _mcp_tools(transcript: Path) -> list[str]:
    tools: list[str] = []
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "mcp_tool_call" and item.get("server") == "ontology_platform":
            tool = item.get("tool")
            if isinstance(tool, str):
                tools.append(tool)
    return tools


def _batch_attempt(detail: dict[str, Any], status: str) -> dict[str, Any]:
    attempts = detail.get("attempts")
    if not isinstance(attempts, list):
        raise L1Error("platform batch detail lacks immutable attempts")
    matches = [attempt for attempt in attempts if isinstance(attempt, dict) and attempt.get("attempt_status") == status]
    if len(matches) != 1:
        raise L1Error(f"platform batch lacks one {status} attempt")
    return matches[0]


def _items_sha256(detail: dict[str, Any]) -> str:
    items = detail.get("items")
    if not isinstance(items, list) or not items:
        raise L1Error("platform batch lacks immutable Items")
    return hashlib.sha256(canonical_json(items)).hexdigest()


def audit_platform_facts(
    base_url: str, admin_key: str, scope: dict[str, str], protocol: dict[str, Any]
) -> dict[str, Any]:
    """Cross-check Agent claims against platform read APIs under the host admin identity."""
    session_id = protocol["build_session_id"]
    if not isinstance(session_id, str):
        raise L1Error("protocol result lacks build session identity")
    session = require_ok(http_request(base_url, "GET", f"/api/build-sessions/{session_id}", key=admin_key))
    summary = session.get("session")
    leases = session.get("leases")
    if not isinstance(summary, dict) or summary.get("status") != "completed":
        raise L1Error("platform Build Session is not terminal completed")
    if not isinstance(leases, list) or any(lease.get("state") != "released" for lease in leases if isinstance(lease, dict)):
        raise L1Error("platform Build Session lease was not released")
    if scope["ontology_id"] not in {lease.get("ontology_id") for lease in leases if isinstance(lease, dict)}:
        raise L1Error("platform Build Session does not own the evaluated Ontology lease")

    structural = protocol["structural"]
    dry_claim, apply_claim = structural["dry_run"], structural["apply"]
    if dry_claim["batch_id"] != apply_claim["batch_id"]:
        raise L1Error("self-reported structural transition uses different immutable batches")
    if dry_claim["client_batch_id"] != apply_claim["client_batch_id"] or dry_claim["items_sha256"] != apply_claim["items_sha256"]:
        raise L1Error("self-reported structural transition has inconsistent immutable identity/hash")
    detail = require_ok(http_request(base_url, "GET", f"/api/modeling-batches/{dry_claim['batch_id']}", key=admin_key))
    if detail.get("build_session_id") != session_id or detail.get("ontology_id") != scope["ontology_id"]:
        raise L1Error("structural Batch is outside the owned Build Session/Ontology")
    if detail.get("batch_status") != "applied" or detail.get("client_batch_id") != dry_claim["client_batch_id"]:
        raise L1Error("structural Batch identity/status does not match platform facts")
    actual_items_hash = _items_sha256(detail)
    if actual_items_hash != dry_claim["items_sha256"]:
        raise L1Error("structural immutable Items hash differs from platform facts")
    dry_attempt, apply_attempt = _batch_attempt(detail, "validated"), _batch_attempt(detail, "applied")
    if dry_attempt.get("mode") != "dry_run" or apply_attempt.get("mode") != "apply_atomic":
        raise L1Error("structural Batch attempt modes are not dry-run then apply-atomic")
    before, after = apply_attempt.get("workspace", {}).get("before_version"), apply_attempt.get("workspace", {}).get("after_version")
    if before != protocol["workspace"]["before"] or after != protocol["workspace"]["after"] or before == after:
        raise L1Error("platform workspace transition differs from protocol result")

    negative = protocol["negative_dry_run"]
    invalid_detail = require_ok(http_request(base_url, "GET", f"/api/modeling-batches/{negative['batch_id']}", key=admin_key))
    invalid_attempt = _batch_attempt(invalid_detail, "validation_failed")
    if invalid_detail.get("build_session_id") != session_id or invalid_detail.get("batch_status") == "applied":
        raise L1Error("negative candidate was not retained as failed dry-run only")
    if invalid_attempt.get("mode") != "dry_run":
        raise L1Error("negative candidate was not a dry-run")

    # This REST read proves the required modeled resources and their distinct topology, not merely
    # an Agent-authored boolean or that an endpoint returned a JSON object.
    generic = require_ok(http_request(base_url, "GET", f"/api/ontologies/{scope['ontology_id']}/semantic-read-models/entities", key=admin_key))
    rows = generic.get("items")
    if not isinstance(rows, list):
        raise L1Error("generic semantic read lacks entity rows")
    encoded = canonical_json(rows).decode("utf-8")
    required = ("SyntheticReleaseWorkflow", "Current Draft", "Latest Version")
    if any(value not in encoded for value in required):
        raise L1Error("generic read does not contain distinct Workflow/draft/latest resources")
    structural_items = detail.get("items")
    if not isinstance(structural_items, list):
        raise L1Error("structural Batch lacks relation evidence")
    relation_payloads = [item.get("payload", {}) for item in structural_items if isinstance(item, dict) and item.get("command_kind") == "create_relation"]
    relation_text = canonical_json(relation_payloads).decode("utf-8")
    if "SyntheticReleaseWorkflowCurrentDraft" not in relation_text or "SyntheticReleaseWorkflowLatestVersion" not in relation_text or "CurrentDraft" not in relation_text or "LatestVersion" not in relation_text:
        raise L1Error("immutable Batch does not prove distinct synthetic version-state links")
    return {
        "build_session": {"id": session_id, "status": summary["status"], "lease_state": "released"},
        "structural_batch": {"id": detail["batch_id"], "items_sha256": actual_items_hash, "attempts": [dry_attempt["attempt_status"], apply_attempt["attempt_status"]]},
        "negative_batch": {"id": invalid_detail["batch_id"], "attempt_status": invalid_attempt["attempt_status"]},
        "generic_read": True,
    }


def audit_s1_rollouts(paths: dict[str, Path], coordinator_thread_id: str, protocol_thread_id: str) -> dict[str, Any]:
    coordinator = paths["transcripts"] / "s1-coordinator.jsonl"
    protocol = paths["transcripts"] / "s1-protocol.jsonl"
    if _thread_id(coordinator) != coordinator_thread_id or _thread_id(protocol) != protocol_thread_id:
        raise L1Error("rollout identity does not match the launched Agent sessions")
    rollouts = sorted((paths["coordinator_home"] / "sessions").rglob("*.jsonl"))
    child_threads = {_thread_id(path) for path in rollouts} - {coordinator_thread_id}
    if len(child_threads) != 1:
        raise L1Error("S1 lacks one distinct modeling child rollout identity")
    child_rollout = next(path for path in rollouts if _thread_id(path) in child_threads)
    if _contains_mcp_call(coordinator) or _contains_mcp_call(child_rollout):
        raise L1Error("coordinator rollout invoked the platform MCP")
    tools = _mcp_tools(protocol)
    allowed, required = set(PROTOCOL_TOOLS), {"check_platform_health", "get_modeling_context", "create_build_session", "acquire_ontology_lease", "submit_modeling_batch", "get_modeling_batch", "get_ontology_read_model", "save_build_checkpoint", "complete_build_session", "get_build_session"}
    if not tools or set(tools) - allowed or not required.issubset(tools):
        raise L1Error("protocol rollout MCP calls are missing, unapproved, or incomplete")
    return {"coordinator_thread_id": coordinator_thread_id, "modeling_child_thread_id": child_threads.pop(), "protocol_thread_id": protocol_thread_id, "coordinator_mcp_calls": False, "protocol_mcp_tools": sorted(set(tools))}


def audit_coordinator_closure(paths: dict[str, Path], coordinator_thread_id: str, task_id: str) -> dict[str, Any]:
    transcript = paths["transcripts"] / "s1-coordinator-closure.jsonl"
    if _thread_id(transcript) != coordinator_thread_id:
        raise L1Error("closure did not resume the original coordinator Session")
    closure = json.loads((paths["coordinator_work"] / "coordinator-closure.json").read_text(encoding="utf-8"))
    expected = {"task_id": task_id, "coordinator_thread_id": coordinator_thread_id, "state": "CLOSED", "marker": "L1_COORDINATOR_CLOSED"}
    if closure != expected or "L1_COORDINATOR_CLOSED" not in transcript.read_text(encoding="utf-8", errors="replace"):
        raise L1Error("coordinator closure marker/evidence is invalid")
    return closure


def run(run_id: str, *, execute: bool) -> dict[str, Any]:
    if not execute:
        raise L1Error("refusing live L1 mutation without --execute")
    if not CODEX_BINARY.is_file() or not HOST_CODEX_AUTH.is_file():
        raise L1Error("Codex executable or host provider authentication is unavailable")
    directory = run_dir(run_id)
    if directory.exists():
        raise L1Error("run directory already exists")
    manifest = read_manifest()
    paths = paths_for(directory)
    state: dict[str, Any] = {"run_id": run_id, "state": "INCONCLUSIVE", "started_at": now()}
    admin_key: str | None = None
    model_key: str | None = None
    rest: subprocess.Popen[str] | None = None
    try:
        directory.mkdir(mode=0o700, parents=True)
        for name in ("coordinator_work", "protocol_work", "transcripts", "audit"):
            paths[name].mkdir(mode=0o700)
        # S0 is deliberately before isolated REST, admin bootstrap, Project, Ontology and model key.
        state["coordinator_stage"] = stage_input(manifest, paths["coordinator_input"])
        write_coordinator_config(paths["coordinator_home"])
        verify_strict_config(paths, "coordinator", {})
        s0_prompt = (AGENT_INPUT / "coordinator-task.md").read_text(encoding="utf-8") + "\nThis is L1-S0 only.\n"
        state["s0_execution"] = execute_agent(paths, "coordinator", s0_prompt, paths["transcripts"] / "s0.jsonl", {})
        state["s0"] = audit_s0(paths)
        write_json(paths["audit"] / "s0-audit.json", state["s0"])
        shutil.rmtree(paths["coordinator_work"])
        paths["coordinator_work"].mkdir(mode=0o700)
        settings = sanitized_settings()
        state["config_probe"] = probe_sanitized_configuration(paths, settings)
        port = choose_port(run_id)
        rest = start_isolated_rest(paths, settings, port)
        base_url = f"http://127.0.0.1:{port}"
        state["isolated_rest_health"] = require_ok(http_request(base_url, "GET", "/api/health"))
        admin_key, admin_audit = bootstrap_admin()
        state["host_admin"] = admin_audit
        mode = require_ok(http_request(base_url, "GET", "/api/semantic/canonical-mode", key=admin_key))
        if mode.get("product_write_mode") != "rdf_primary":
            raise L1Error("isolated REST canonical mode is not rdf_primary")
        project = require_ok(http_request(base_url, "POST", "/api/projects", {"name": f"R2.2 L1 {run_id}", "description": f"owned L1 run {run_id}"}, admin_key))
        project_id = project.get("id")
        if not isinstance(project_id, str):
            raise L1Error("owned Project creation lacked id")
        ontology = require_ok(http_request(base_url, "POST", f"/api/projects/{project_id}/ontologies", {"name": f"L1 {run_id}", "description": "owned L1 ontology", "external_mappings": {}}, admin_key))
        ontology_id = ontology.get("id")
        if not isinstance(ontology_id, str):
            raise L1Error("owned Ontology creation lacked id")
        state["scope"] = {"project_id": project_id, "ontology_id": ontology_id}
        state["s1_coordinator"] = execute_agent(paths, "coordinator", (AGENT_INPUT / "coordinator-task.md").read_text(encoding="utf-8") + "\nThis is L1-S1 only.\n", paths["transcripts"] / "s1-coordinator.jsonl", settings)
        candidate, dispatch = _candidate_and_dispatch(paths["coordinator_work"])
        write_json(paths["audit"] / "coordinator-dispatch.json", dispatch)
        paths["protocol_input"].mkdir(mode=0o700)
        write_json(paths["protocol_input"] / "approved-candidate.json", candidate, mode=0o444)
        write_json(paths["protocol_input"] / "protocol-dispatch.json", dispatch, mode=0o444)
        write_json(
            paths["protocol_input"] / "protocol-scope.json",
            {"project_id": project_id, "ontology_id": ontology_id},
            mode=0o444,
        )
        shutil.copyfile(AGENT_INPUT / "public-protocol.md", paths["protocol_input"] / "public-protocol.md")
        os.chmod(paths["protocol_input"] / "public-protocol.md", 0o444)
        created_key = require_ok(http_request(base_url, "POST", "/api/api-keys", {"name": f"r2-2-001-l1-model-{run_id}", "project_id": project_id, "scopes": ["model"]}, admin_key))
        model_key = created_key.pop("plaintext_key", None)
        if not isinstance(model_key, str) or not isinstance(created_key.get("id"), str):
            raise L1Error("Project-scoped protocol key creation failed")
        state["protocol_key"] = {"key_id": created_key["id"], "project_id": project_id, "scope": "model"}
        write_protocol_config(paths["protocol_home"], model_key, settings)
        verify_strict_config(paths, "protocol", settings)
        probe_mcp_requires_run_key(paths, settings)
        state["mcp_no_key_authentication"] = "rejected"
        prompt = "You are the isolated Platform Protocol Agent. Read /opt including protocol-scope.json and use only ontology_platform MCP tools permitted by the public protocol. The approved coordinator dispatch is your sole semantic authorization; protocol-scope.json supplies only the owned Project/Ontology identifiers. Complete the protocol and write /work/protocol-result.json."
        state["s1_protocol"] = execute_agent(paths, "protocol", prompt, paths["transcripts"] / "s1-protocol.jsonl", settings)
        protocol_result = validate_protocol_result(
            json.loads((paths["protocol_work"] / "protocol-result.json").read_text(encoding="utf-8"))
        )
        state["s1_rollout_audit"] = audit_s1_rollouts(
            paths,
            state["s1_coordinator"]["thread_id"],
            state["s1_protocol"]["thread_id"],
        )
        state["platform_fact_audit"] = audit_platform_facts(base_url, admin_key, state["scope"], protocol_result)
        write_json(paths["audit"] / "s1-rollout-audit.json", state["s1_rollout_audit"])
        write_json(paths["audit"] / "platform-fact-audit.json", state["platform_fact_audit"])
        normalized_result = {
            "task_id": dispatch["task_id"],
            "protocol_result_sha256": hashlib.sha256(canonical_json(protocol_result)).hexdigest(),
            "platform_fact_audit_sha256": hashlib.sha256(canonical_json(state["platform_fact_audit"])).hexdigest(),
        }
        closure_prompt = (
            "You are resuming the original L1-S1 coordinator Session. The launcher has independently "
            "audited the protocol result. You must not call MCP or create any further candidate or Modeling "
            "Item. Receive only this normalized result: "
            f"{canonical_json(normalized_result).decode('utf-8')}. "
            "Write /work/coordinator-closure.json with exactly task_id, coordinator_thread_id, state, marker; "
            f"use task_id {dispatch['task_id']}, your current coordinator_thread_id, state CLOSED, and marker "
            "L1_COORDINATOR_CLOSED. Output exactly L1_COORDINATOR_CLOSED."
        )
        state["s1_coordinator_closure_execution"] = execute_agent(
            paths,
            "coordinator",
            closure_prompt,
            paths["transcripts"] / "s1-coordinator-closure.jsonl",
            {},
            session_id=state["s1_coordinator"]["thread_id"],
        )
        state["coordinator_closure"] = audit_coordinator_closure(
            paths, state["s1_coordinator"]["thread_id"], dispatch["task_id"]
        )
        write_json(paths["audit"] / "coordinator-closure-audit.json", state["coordinator_closure"])
        scan = scan_forbidden([paths["transcripts"], paths["audit"], paths["protocol_work"]], model_key)
        if not scan["passed"]:
            raise L1Error("credential or host path entered L1 evidence")
        state.update({"state": "PASS", "protocol_result_sha256": hashlib.sha256(canonical_json(protocol_result)).hexdigest(), "updated_at": now()})
    except Exception as exc:
        state.update({"state": "INCONCLUSIVE", "error": str(exc), "updated_at": now()})
        raise
    finally:
        try:
            if state.get("protocol_key", {}).get("key_id"):
                revoke = http_request(f"http://127.0.0.1:{choose_port(run_id)}", "POST", f"/api/api-keys/{state['protocol_key']['key_id']}:revoke", key=admin_key)
                state["protocol_key"]["revoked"] = bool(revoke.get("status") == 200 and revoke.get("body", {}).get("revoked_at"))
            if admin_key and state.get("scope", {}).get("project_id"):
                project_id = state["scope"]["project_id"]
                response = http_request(f"http://127.0.0.1:{choose_port(run_id)}", "DELETE", f"/api/projects/{project_id}", key=admin_key)
                state["cleanup_project"] = {"project_id": project_id, "deleted": response.get("status") == 204}
            if state.get("host_admin", {}).get("key_id"):
                state["host_admin"]["revoked"] = bootstrap_revoke(state["host_admin"]["key_id"])
            stop_process(rest)
            write_json(paths["audit"] / "state.json", state)
        finally:
            if model_key:
                model_key = None
            if admin_key:
                admin_key = None
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    child = parser.add_subparsers(dest="command", required=True)
    run_parser = child.add_parser("run")
    run_parser.add_argument("--run-id", required=True)
    run_parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        result = run(args.run_id, execute=args.execute)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except L1Error as exc:
        print(f"L1 error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
