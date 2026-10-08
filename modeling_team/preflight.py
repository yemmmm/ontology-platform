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
from .r23003_contract import (
    R2_3_003_TARGET_CLASS,
    R2_3_003_TARGET_IDS,
    validate_deletion_policy,
)


_FORMAL_SCOPE_KEYS = frozenset({"mode"})
_REQUIRED_ENV = {
    "SEMANTIC_CANONICAL_STORE": "rdf",
    "SEMANTIC_PRODUCT_WRITE_MODE": "rdf_primary",
    "SEMANTIC_READ_MODE": "canonical",
}
_DELIVERY_ADMIN_ENV = "ONTOLOGY_PLATFORM_ADMIN_API_KEY"
R2_3_003_PROJECT_ID = "7fc146d8-c76f-417b-9314-854544f269fc"
R2_3_003_ONTOLOGY_ID = "fd762f52-2f5e-4bc0-902a-5583135ab64d"
R2_3_003_HANDOFF_RELATIVE = "modeling_team/scopes/r2-3-003-start75-handoff.json"
_R2_3_003_SCOPE_KEYS = frozenset({"mode", "project_id", "ontology_id", "handoff_path"})
_R2_3_003_HANDOFF_KEYS = frozenset(
    {
        "run_id",
        "project_id",
        "ontology_id",
        "model_revision",
        "scope_disposition",
        "deletion_policy",
    }
)


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


def normalize_existing_scope(value: Any) -> dict[str, str]:
    """Validate the frozen R2.3-003 Start75 scope identity.

    This is intentionally separate from ``normalize_formal_scope`` so the
    R2.3-005 create contract cannot be widened by passing IDs through a shared
    generic scope parser.
    """

    if not isinstance(value, Mapping):
        raise TeamConfigurationError("existing scope must be a YAML object")
    if set(value) != _R2_3_003_SCOPE_KEYS:
        raise TeamConfigurationError("R2.3-003 existing scope fields drift")
    if value.get("mode") != "existing":
        raise TeamConfigurationError("R2.3-003 scope requires mode=existing")
    if value.get("project_id") != R2_3_003_PROJECT_ID:
        raise TeamConfigurationError("R2.3-003 Project identity drifts")
    if value.get("ontology_id") != R2_3_003_ONTOLOGY_ID:
        raise TeamConfigurationError("R2.3-003 Ontology identity drifts")
    handoff_path = value.get("handoff_path")
    if handoff_path != R2_3_003_HANDOFF_RELATIVE:
        raise TeamConfigurationError("R2.3-003 handoff path drifts")
    return {
        "mode": "existing",
        "project_id": R2_3_003_PROJECT_ID,
        "ontology_id": R2_3_003_ONTOLOGY_ID,
        "handoff_path": R2_3_003_HANDOFF_RELATIVE,
    }


def normalize_scope_for_contract(value: Any, scope_mode: str) -> dict[str, str]:
    if scope_mode == "create":
        return normalize_formal_scope(value)
    if scope_mode == "existing":
        return normalize_existing_scope(value)
    raise TeamConfigurationError("formal scope mode is unsupported")


def load_existing_scope_handoff(scope: Mapping[str, str], *, repository_root: Path) -> dict[str, str]:
    """Load the exact non-sensitive handoff and reject path/digest drift."""

    normalized = normalize_existing_scope(scope)
    path = repository_root / normalized["handoff_path"]
    try:
        resolved = path.resolve()
        root = repository_root.resolve()
        if root not in resolved.parents or path.is_symlink() or not path.is_file():
            raise TeamConfigurationError("R2.3-003 handoff is unavailable")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TeamConfigurationError("R2.3-003 handoff is unreadable") from exc
    if isinstance(value, Mapping) and "workspace_version" in value:
        raise TeamConfigurationError("legacy_model_binding: re-read the retained scope and prepare a new numbered handoff; original evidence remains unchanged")
    if not isinstance(value, Mapping) or set(value) != _R2_3_003_HANDOFF_KEYS:
        raise TeamConfigurationError("R2.3-003 handoff fields drift")
    if (
        value.get("project_id") != normalized["project_id"]
        or value.get("ontology_id") != normalized["ontology_id"]
        or value.get("scope_disposition") != "retained"
    ):
        raise TeamConfigurationError("R2.3-003 handoff scope binding drifts")
    try:
        policy = validate_deletion_policy(value.get("deletion_policy"))
    except ValueError as exc:
        raise TeamConfigurationError(str(exc)) from exc
    if tuple(item["semantic_id"] for item in policy["targets"]) != R2_3_003_TARGET_IDS:
        raise TeamConfigurationError("R2.3-003 handoff target IDs drift")
    if any(item["expected_class"] != R2_3_003_TARGET_CLASS for item in policy["targets"]):
        raise TeamConfigurationError("R2.3-003 handoff target Class drifts")
    for field in ("run_id",):
        item = value.get(field)
        if not isinstance(item, str) or not item.strip():
            raise TeamConfigurationError("R2.3-003 handoff value is invalid")
    if type(value.get("model_revision")) is not int or value["model_revision"] < 0:
        raise TeamConfigurationError("R2.3-003 model revision is invalid")
    return {
        "run_id": str(value["run_id"]),
        "project_id": str(value["project_id"]),
        "ontology_id": str(value["ontology_id"]),
        "model_revision": value["model_revision"],
        "scope_disposition": "retained",
        "deletion_policy": policy,
    }


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


def _digest_text(value: str | bytes) -> str:
    import hashlib

    payload = value if isinstance(value, bytes) else value.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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
        "project_id",
        "ontology_id",
        "run_id",
        "model_revision",
        "ontology_id",
        "workspace_state",
        "modeling_batch_count",
        "recent_session_count",
        "active_session_count",
        "active_lease_count",
        "in_flight_attempt_count",
        "scope_disposition",
        "handoff",
        "live",
        "ownership",
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


def _authenticated_json_get(base_url: str, admin_key: str, path: str) -> Any:
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        method="GET",
        headers={"Authorization": f"Bearer {admin_key}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status != 200:
                raise TeamConfigurationError("existing scope live read failed")
            return json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        try:
            exc.read()
        except OSError:
            pass
        raise TeamConfigurationError("existing scope live read failed") from exc
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise TeamConfigurationError("existing scope live read failed") from exc


def _model_revision(context: Mapping[str, Any]) -> int | None:
    workspace = context.get("workspace")
    value = workspace.get("model_revision") if isinstance(workspace, Mapping) else context.get("model_revision")
    return value if type(value) is int and value >= 0 else None


def canonical_existing_scope_preflight(
    *,
    scope: Mapping[str, str],
    handoff: Mapping[str, str],
    base_url: str,
    admin_key: str,
) -> dict[str, Any]:
    """Read and validate the live retained Project/Ontology before side effects."""

    normalized = normalize_existing_scope(scope)
    project_id, ontology_id = normalized["project_id"], normalized["ontology_id"]
    if not isinstance(admin_key, str) or not admin_key:
        raise TeamConfigurationError("existing scope credential is unavailable")
    project = _authenticated_json_get(base_url, admin_key, f"/api/projects/{project_id}")
    if not isinstance(project, Mapping) or project.get("id") != project_id:
        raise TeamConfigurationError("existing Project identity drifts")
    listed = _authenticated_json_get(base_url, admin_key, f"/api/projects/{project_id}/ontologies")
    if isinstance(listed, Mapping):
        listed_items = listed.get("items", listed.get("ontologies", []))
    else:
        listed_items = listed
    if not isinstance(listed_items, list) or not any(
        isinstance(item, Mapping) and item.get("id") == ontology_id for item in listed_items
    ):
        raise TeamConfigurationError("existing Ontology ownership drifts")
    context = _authenticated_json_get(
        base_url, admin_key, f"/api/ontologies/{ontology_id}/workspace-context"
    )
    if not isinstance(context, Mapping) or context.get("state") != "ready":
        raise TeamConfigurationError("existing ontology workspace is not ready")
    ontology_id = context.get("ontology_id")
    if ontology_id is None:
        raise TeamConfigurationError("existing default Graph Set is unavailable")

    batches = _authenticated_json_get(
        base_url, admin_key, f"/api/ontologies/{ontology_id}/modeling-batches"
    )
    batch_items = batches.get("items", batches.get("batches", [])) if isinstance(batches, Mapping) else batches
    if not isinstance(batch_items, list):
        raise TeamConfigurationError("existing Modeling Batch history is invalid")
    build = _authenticated_json_get(base_url, admin_key, f"/api/projects/{project_id}/build-context")
    live_version = _model_revision(context)
    if live_version is None and isinstance(build, Mapping):
        platform_state = build.get("platform_state")
        ontologies = platform_state.get("ontologies", []) if isinstance(platform_state, Mapping) else []
        for ontology in ontologies if isinstance(ontologies, list) else []:
            if not isinstance(ontology, Mapping) or ontology.get("id") != ontology_id:
                continue
            workspace = ontology.get("workspace")
            if isinstance(workspace, Mapping):
                live_version = workspace.get("model_revision")
            break
    if live_version != handoff.get("model_revision"):
        raise TeamConfigurationError("existing workspace version drifts from handoff")
    agent_state = build.get("agent_state") if isinstance(build, Mapping) else None
    if not isinstance(agent_state, Mapping):
        raise TeamConfigurationError("existing Build Context agent state is invalid")
    active_sessions = agent_state.get("active_sessions", [])
    recent_sessions = agent_state.get("recent_sessions", [])
    active_leases = agent_state.get("active_leases", agent_state.get("leases", []))
    in_flight = agent_state.get("in_flight_attempts", agent_state.get("inflight_attempts", []))
    if not isinstance(active_sessions, list) or not isinstance(recent_sessions, list):
        raise TeamConfigurationError("existing Build Session state is invalid")
    if not isinstance(active_leases, list) or not isinstance(in_flight, list):
        raise TeamConfigurationError("existing Lease/Attempt state is invalid")
    if active_sessions or active_leases or in_flight:
        raise TeamConfigurationError("existing scope has active Session, Lease, or Attempt")
    fence = agent_state.get("fence")
    if isinstance(fence, Mapping) and fence.get("active") is True:
        raise TeamConfigurationError("existing scope has an active fence")
    for session in recent_sessions:
        if not isinstance(session, Mapping):
            continue
        session_id = session.get("id", session.get("session_id"))
        if not isinstance(session_id, str) or not session_id:
            continue
        details = _authenticated_json_get(base_url, admin_key, f"/api/build-sessions/{session_id}")
        if not isinstance(details, Mapping):
            raise TeamConfigurationError("existing Build Session detail is invalid")
        leases = details.get("leases", [])
        if isinstance(leases, list) and any(
            isinstance(lease, Mapping) and lease.get("state") not in {"released", "expired", "cancelled"}
            for lease in leases
        ):
            raise TeamConfigurationError("existing scope has an active Lease")
        status = str(details.get("status", details.get("state", ""))).lower()
        if status in {"active", "running", "in_progress", "applying", "recovering", "leased"}:
            raise TeamConfigurationError("existing scope has an in-flight Build Session")
    return {
        "project_id": project_id,
        "workspace_state": context.get("state"),
        "model_revision": live_version,
        "ontology_id": ontology_id,
        "modeling_batch_count": len(batch_items),
        "recent_session_count": len(recent_sessions),
        "active_session_count": len(active_sessions),
        "active_lease_count": len(active_leases),
        "in_flight_attempt_count": len(in_flight),
        "scope_disposition": "retained",
    }


def run_existing_scope_preflight(
    *,
    repository_root: Path,
    scope: Mapping[str, str],
    base_url: str = "http://127.0.0.1:8001",
    admin_key: str | None = None,
    probe: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run clean-checkout, exact handoff, and live retained-scope checks."""

    checkout = capture_clean_checkout(repository_root)
    normalized = normalize_existing_scope(scope)
    handoff = load_existing_scope_handoff(normalized, repository_root=repository_root)
    if not isinstance(admin_key, str) or not admin_key:
        raise TeamConfigurationError("existing scope credential is unavailable")
    if probe is None:
        live = canonical_existing_scope_preflight(
            scope=normalized, handoff=handoff, base_url=base_url, admin_key=admin_key
        )
    else:
        try:
            live = probe(
                scope=normalized,
                handoff=handoff,
                repository_root=repository_root,
                base_url=base_url,
                admin_key=admin_key,
            )
        except TypeError:
            live = probe()
        if not isinstance(live, Mapping):
            raise TeamConfigurationError("injected existing preflight must return an object")
        live = dict(live)
        if live.get("project_id", normalized["project_id"]) != normalized["project_id"]:
            raise TeamConfigurationError("injected existing Project identity drifts")
        if live.get("ontology_id", normalized["ontology_id"]) != normalized["ontology_id"]:
            raise TeamConfigurationError("injected existing Ontology identity drifts")
        live_version = live.get("model_revision")
        if live_version is not None and live_version != handoff["model_revision"]:
            raise TeamConfigurationError("injected existing workspace version drifts")
    return {
        "checkout": _sanitize_evidence(checkout),
        "scope": _sanitize_evidence(dict(normalized)),
        "handoff": _sanitize_evidence(dict(handoff)),
        "live": _sanitize_evidence(dict(live)),
    }


__all__ = [
    "capture_clean_checkout",
    "canonical_platform_preflight",
    "canonical_existing_scope_preflight",
    "load_existing_scope_handoff",
    "normalize_formal_scope",
    "normalize_existing_scope",
    "normalize_scope_for_contract",
    "run_existing_scope_preflight",
    "run_prestart_preflight",
]
