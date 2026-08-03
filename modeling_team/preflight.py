"""No-start gates for the formal R2.3-005 Runner entrypoint.

The preflight is deliberately read-only.  It validates the prospective scope and
the checkout before ``StartLedger.reserve`` or the PlatformScope is touched.  The
process/service probe is injectable so deterministic tests can exercise the same
ordering without requiring a live platform service; the default probe is the
operator-facing local service check used by the real CLI.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .acceptance import AcceptanceContractError, canonical_mode_preflight
from .contracts import TeamConfigurationError


_FORMAL_SCOPE_KEYS = frozenset({"mode"})
_REQUIRED_ENV = {
    "SEMANTIC_CANONICAL_STORE": "rdf",
    "SEMANTIC_PRODUCT_WRITE_MODE": "rdf_primary",
    "SEMANTIC_READ_MODE": "canonical",
}
_DELIVERY_ADMIN_ENV = "ONTOLOGY_PLATFORM_ADMIN_API_KEY"


def normalize_formal_scope(value: Any) -> dict[str, str]:
    """Normalize the only supported R2.3-005 scope: a fresh empty scope.

    IDs are intentionally not accepted here.  Allowing a caller to smuggle an
    existing Project/Ontology through the generic ``PlatformScope`` would turn
    this task into the deferred existing-scope workflow.
    """

    if not isinstance(value, Mapping):
        raise TeamConfigurationError("formal scope must be a YAML object")
    if value.get("mode") != "create":
        raise TeamConfigurationError("R2.3-005 formal scope requires mode=create")
    unexpected = set(value) - _FORMAL_SCOPE_KEYS
    if unexpected:
        names = ", ".join(sorted(str(item) for item in unexpected))
        raise TeamConfigurationError(f"R2.3-005 formal scope contains unsupported fields: {names}")
    return {"mode": "create"}


def _run_checked(args: list[str], *, cwd: Path) -> str:
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except (OSError, ValueError) as exc:
        raise TeamConfigurationError("preflight command unavailable") from exc
    if completed.returncode != 0:
        raise TeamConfigurationError("preflight command failed")
    return completed.stdout


def capture_clean_checkout(root: Path) -> dict[str, str]:
    """Capture HEAD and status, requiring an empty worktree."""

    head = _run_checked(["git", "rev-parse", "HEAD"], cwd=root).strip()
    if not head:
        raise TeamConfigurationError("git HEAD is unavailable")
    status = _run_checked(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root)
    if status.strip():
        raise TeamConfigurationError("clean baseline gate rejected non-empty git status")
    return {
        "head": head,
        "status_porcelain": "",
        "status_digest": _digest_text(status),
    }


def _digest_text(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _service_properties(text: str) -> dict[str, str]:
    properties: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        properties[key.strip()] = value.strip()
    return properties


def _service_probe() -> dict[str, Any]:
    unit = "ontology-platform.service"
    show = _run_checked(
        [
            "systemctl",
            "--user",
            "show",
            unit,
            "--no-pager",
            "--property=ActiveState,SubState,MainPID,ActiveEnterTimestamp",
        ],
        cwd=Path.cwd(),
    )
    properties = _service_properties(show)
    if properties.get("ActiveState") != "active" or properties.get("SubState") != "running":
        raise TeamConfigurationError("ontology-platform.service is not active/running")
    try:
        pid = int(properties.get("MainPID", "0"))
    except ValueError as exc:
        raise TeamConfigurationError("ontology-platform.service MainPID is invalid") from exc
    if pid <= 0:
        raise TeamConfigurationError("ontology-platform.service MainPID is unavailable")
    return {
        "unit": unit,
        "active_state": properties.get("ActiveState"),
        "sub_state": properties.get("SubState"),
        "main_pid": pid,
        "active_enter_timestamp": properties.get("ActiveEnterTimestamp", ""),
    }


def _process_probe(
    pid: int,
    *,
    unit: str,
    started_at: str,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    proc = Path("/proc") / str(pid)
    try:
        environ_bytes = (proc / "environ").read_bytes()
        cwd = os.readlink(proc / "cwd")
        command = (proc / "cmdline").read_bytes().replace(b"\x00", b" ").decode(
            "utf-8", errors="replace"
        ).strip()
        cgroup = (proc / "cgroup").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise TeamConfigurationError("active service process evidence is unavailable") from exc
    if unit not in cgroup:
        raise TeamConfigurationError("active service process is not bound to the service unit")
    if repository_root is not None:
        resolved_cwd = Path(cwd).resolve()
        resolved_root = repository_root.resolve()
        if resolved_cwd != resolved_root and resolved_root not in resolved_cwd.parents:
            raise TeamConfigurationError("active service process is not bound to the repository")
    env: dict[str, str] = {}
    for entry in environ_bytes.split(b"\x00"):
        if b"=" not in entry:
            continue
        key, value = entry.split(b"=", 1)
        if key.decode("utf-8", errors="ignore") in _REQUIRED_ENV:
            env[key.decode("utf-8")] = value.decode("utf-8", errors="replace")
    if any(env.get(key) != value for key, value in _REQUIRED_ENV.items()):
        raise TeamConfigurationError("active service process environment is not canonical")
    return {
        "unit": unit,
        "pid": pid,
        "started_at": started_at,
        "cwd_digest": _digest_text(cwd),
        "command_digest": _digest_text(command),
        "cgroup_digest": _digest_text(cgroup),
        "process_env": {key: env[key] for key in sorted(_REQUIRED_ENV)},
    }


def _public_http_get(base_url: str, path: str) -> tuple[int, bytes]:
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        method="GET",
        headers={"Accept": "application/json,text/html"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        # Keep the response body out of evidence and expose only the status to
        # the fixed preflight error below.
        try:
            exc.read()
        except OSError:
            pass
        return exc.code, b""
    except (OSError, ValueError) as exc:
        raise TeamConfigurationError("health endpoint probe failed") from exc


def _health_probe(base_url: str, *, path: str, endpoint_role: str) -> dict[str, Any]:
    status_code, body = _public_http_get(base_url, path)
    if status_code != 200:
        raise TeamConfigurationError(f"{endpoint_role} health preflight failed")
    return {
        "endpoint_role": endpoint_role,
        "status_code": status_code,
        "body_digest": _digest_text(body),
    }


def _canonical_http_get(base_url: str, admin_key: str) -> tuple[int, Any]:
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/semantic/canonical-mode",
        method="GET",
        headers={"Authorization": f"Bearer {admin_key}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = response.read()
            return response.status, json.loads(payload or b"null")
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read() or b"null")
        except (OSError, ValueError, json.JSONDecodeError):
            payload = None
        return exc.code, payload
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise TeamConfigurationError("canonical-mode authenticated probe failed") from exc


def canonical_platform_preflight(
    *,
    base_url: str = "http://127.0.0.1:8001",
    frontend_base_url: str | None = None,
    admin_key: str | None = None,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Capture service/process/config binding and authenticated canonical-mode response."""

    service = _service_probe()
    process = _process_probe(
        int(service["main_pid"]),
        unit=str(service["unit"]),
        started_at=str(service["active_enter_timestamp"]),
        repository_root=repository_root,
    )
    backend_health = _health_probe(base_url, path="/api/health", endpoint_role="backend-health")
    frontend_health = _health_probe(
        frontend_base_url or base_url.replace(":8001", ":5173"),
        path="/",
        endpoint_role="frontend-root",
    )
    key = admin_key if admin_key is not None else os.environ.get(_DELIVERY_ADMIN_ENV)
    if not key:
        raise TeamConfigurationError("Delivery-only admin credential is unavailable for canonical preflight")
    status_code, response = _canonical_http_get(base_url, key)
    if not isinstance(response, Mapping):
        raise TeamConfigurationError("canonical-mode response is not an object")
    try:
        canonical = canonical_mode_preflight(
            response=response,
            status_code=status_code,
            unit=str(service["unit"]),
            pid=int(service["main_pid"]),
            started_at=str(service["active_enter_timestamp"]),
            process_env=process["process_env"],
        )
    except AcceptanceContractError as exc:
        raise TeamConfigurationError("canonical-mode preflight failed") from exc
    response = canonical.get("response", {})
    safe_response = {
        field: response[field]
        for field in ("canonical_store", "product_write_mode", "read_mode", "legacy_write_blocked")
        if field in response
    }
    # ``canonical_mode_preflight`` already strips secrets.  Keep only the fixed
    # response fields and service/process binding in immutable evidence.
    return {
        "health": {"backend": backend_health, "frontend": frontend_health},
        "canonical": {
            "status_code": canonical["status_code"],
            "response": safe_response,
            "response_digest": canonical["digest"],
            "unit": canonical["unit"],
            "pid": canonical["pid"],
            "started_at": canonical["started_at"],
            "process_env": canonical["process_env"],
        },
        "service": service,
        "process": process,
    }


def _sanitize_evidence(value: Any) -> Any:
    """Retain only path/credential-free preflight fields from injected probes."""

    blocked_tokens = ("path", "root", "secret", "token", "credential", "password", "key")
    safe_keys = {
        "checkout",
        "head",
        "status_porcelain",
        "status_digest",
        "canonical",
        "response",
        "response_digest",
        "status_code",
        "canonical_store",
        "product_write_mode",
        "read_mode",
        "legacy_write_blocked",
        "unit",
        "active_state",
        "sub_state",
        "main_pid",
        "active_enter_timestamp",
        "pid",
        "started_at",
        "cwd_digest",
        "command_digest",
        "cgroup_digest",
        "process_env",
        "health",
        "backend",
        "frontend",
        "endpoint_role",
        "body_digest",
        "service",
        "process",
    }
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for raw_key, child in value.items():
            key = str(raw_key)
            lowered = key.lower()
            if key not in safe_keys or any(token in lowered for token in blocked_tokens):
                continue
            output[key] = _sanitize_evidence(child)
        return output
    if isinstance(value, list):
        return [_sanitize_evidence(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_evidence(item) for item in value]
    return value


def run_prestart_preflight(
    *,
    repository_root: Path,
    base_url: str = "http://127.0.0.1:8001",
    admin_key: str | None = None,
    probe: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the no-start gate and return safe, immutable evidence for staging."""

    checkout = capture_clean_checkout(repository_root)
    if probe is None:
        canonical = canonical_platform_preflight(
            base_url=base_url,
            admin_key=admin_key,
            repository_root=repository_root,
        )
    else:
        try:
            canonical = probe(
                repository_root=repository_root,
                base_url=base_url,
                admin_key=admin_key,
            )
        except TypeError:
            # Small test doubles often expose a zero-argument probe.  Retain a
            # strict fallback rather than requiring knowledge of this adapter API.
            canonical = probe()
        if not isinstance(canonical, Mapping):
            raise TeamConfigurationError("injected canonical preflight must return an object")
        canonical = dict(canonical)
    return {
        "checkout": _sanitize_evidence(checkout),
        "canonical": _sanitize_evidence(dict(canonical)),
    }


__all__ = [
    "capture_clean_checkout",
    "canonical_platform_preflight",
    "normalize_formal_scope",
    "run_prestart_preflight",
]
