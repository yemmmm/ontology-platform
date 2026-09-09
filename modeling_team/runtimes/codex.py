"""Codex app-server implementation; its Thread and turn fields stay private here."""

from __future__ import annotations

import hashlib
import json
import os
import re
import select
import shlex
import signal
import socket
import shutil
import subprocess
import stat
import secrets
import threading
import time
import tempfile
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from ..contracts import AgentPackage, digest_file
from ..model_manifest import FORMAL_MODEL_TASK_ID
from ..model_routing import (
    CODEX_AUTH_MODE,
    CODEX_TOML_PROVIDER_ID,
    MODEL_PROFILE_PACKAGE_IDS,
    PROVIDER_CATALOG,
    REQUESTED_EFFORT_TIERS,
    ProviderSessionManager,
    RoleModelBinding,
    TeamModelProfile,
    uses_external_credential_session,
)
from ..deepseek_provider_proxy import DEEPSEEK_API_KEY_ENV
from ..acceptance_runtime import (
    AcceptanceBatchPacket,
    CQ_ACCEPTANCE_BRANCH_V3,
    CQ_ACCEPTANCE_PLATFORM_ROLE,
    ExaminerRolePacket,
    ExaminerRunMetrics,
    ExaminerRuntimeBlocked,
    ReportSinkServer,
    ScopedReadProxy,
    V3BatchReportContract,
    acceptance_branch_for,
    v3_examiner_proxy_schemas,
    v3_proxy_scope_entries,
    v3_ticket_digest,
    _make_report_validator,
    _source_report_evidence_ids,
    _validate_acceptance_evidence_ids,
    _validate_platform_report_receipts,
    examiner_proxy_schemas,
    _packet_canonical,
    _unfreeze_packet,
    _copy_private,
    child_config_digest,
    prepare_child_tree,
)
from ..modeling_readonly import MODELING_READ_TOOLS
from ..capability_mcp import (
    COMPETENCY_QUESTION_ROLE,
    CQ_OPERATION,
    ROLE_OPERATIONS,
    STAGED_PROTOCOL_OPERATION,
)
from ..candidate_platform_gate import (
    CANDIDATE_PLATFORM_GATE_DIR_MOUNT,
    CANDIDATE_PLATFORM_GATE_MOUNT,
    CandidatePlatformGate,
)
from ..protocol_mcp_launch import protocol_mcp_launch_spec
from ..protocol_mechanics import protocol_mechanics_contract_bytes
from ..protocol_retrieval_gate import ORDINARY_RETRIEVAL_RECEIPT_SCHEMA
from ..transport_mcp import TERMINAL_REPORT_GUARD_ERROR
from .base import (
    AgentRuntimeIdentity,
    AgentState,
    RuntimeAdapter,
    RuntimeDelivery,
    RuntimeDispatchReceipt,
    RuntimeMessage,
)


class CodexRuntimeError(RuntimeError):
    pass


_RPC_ERROR_CATEGORIES = frozenset(
    {
        "rpc_error",
        "malformed_rpc_error",
        "no_active_turn_to_steer",
        "active_turn_mismatch",
    }
)


class CodexRuntimeRPCError(CodexRuntimeError):
    """Sanitized JSON-RPC failure returned by the local App Server.

    The App Server's ``data`` field is provider-controlled and deliberately
    discarded.  The ``message`` field is server-generated diagnostics and is
    retained in sanitized form (R2.3-008 start3: a fatal ``-32603`` carried its
    cause only in the dropped message).  Consumers may branch on this closed
    category set and, for the one steer-retry case, use the validated in-memory
    turn ID.
    """

    def __init__(
        self,
        method: str,
        code: int | None,
        category: str,
        *,
        active_turn_id: str | None = None,
        server_message: str | None = None,
    ) -> None:
        if category not in _RPC_ERROR_CATEGORIES:
            category = "rpc_error"
        self.method = method
        self.code = code if isinstance(code, int) and not isinstance(code, bool) else None
        self.category = category
        self.active_turn_id = active_turn_id
        self.server_message = server_message
        code_fragment = str(self.code) if self.code is not None else "unknown"
        text = f"app-server {method} failed ({category}, code={code_fragment})"
        if server_message:
            text = f"{text}: {server_message}"
        super().__init__(text)


# Keep a short compatibility spelling for focused integrations that imported the
# adapter's typed error by the conventional ``RPC`` acronym.
CodexRPCError = CodexRuntimeRPCError


def _sanitize_rpc_message(message: str) -> str | None:
    """Reduce a server-generated JSON-RPC ``message`` to bounded diagnostics text.

    Only whitespace is collapsed and the length capped: the text is the App
    Server's own error explanation (R2.3-008 start3 lost the fatal ``-32603``
    cause entirely because the code path kept only the numeric code).  The
    provider-controlled ``data`` field stays discarded and is never merged in.
    """

    sanitized = " ".join(message.split())
    return sanitized[:240] or None


_RETRIEVAL_BLOCKING_WARNINGS = frozenset(
    {
        "evidence_missing",
        "lineage_missing",
        "lineage_partial",
        "lineage_truncated",
        "legacy_lineage_unavailable",
    }
)

_PRIVATE_AGENT_BASE_ARTIFACT_NAMES = (
    "auth.json",
    "config.toml",
    "runner-capabilities.json",
)
_PRIVATE_FORMAL_AGENT_ARTIFACT_NAMES = (
    "runner-capability.token",
    "runner-capability.sock",
    "runner_capability_mcp.py",
    "modeling-read-proxy.token",
)

_DEEPSEEK_API_KEY_ENV = DEEPSEEK_API_KEY_ENV
_DEEPSEEK_BASE_URL = "https://api.deepseek.com/"
_DEEPSEEK_MODEL = "deepseek-v4-flash"
_DEEPSEEK_PROVIDER = "deepseek"

_SECRET_AUDIT_SUFFIXES = frozenset(
    {
        ".json",
        ".jsonl",
        ".toml",
        ".db",
        ".sqlite",
        ".sqlite3",
        ".wal",
        ".shm",
        ".log",
        ".txt",
        ".yaml",
        ".yml",
        ".sh",
        ".token",
    }
)

_AUTH_SECRET_KEY_NAMES = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "auth_token",
        "client_secret",
        "id_token",
        "private_key",
        "refresh_token",
        "secret",
        "session_token",
        "token",
    }
)

# LLM inactivity timeout.  If a role's App Server emits no notification (streaming
# token, tool call, turn event, ...) for this many seconds while the role is in a
# running turn, the model endpoint is treated as hung: the role process is killed and
# the run fails fast as ``runtime/infrastructure``.  Unlike the Examiner child watchdog
# (an absolute deadline) this is an inactivity timer driven by observed stdout activity.
_LLM_INACTIVITY_TIMEOUT_SECONDS = 300.0

# These are the current App Server notification methods whose payloads represent
# actual turn/item/tool work.  Keep this explicit: generic status, warning,
# startup, and unknown notifications must not postpone the inactivity watchdog.
_PROGRESS_NOTIFICATION_METHODS = frozenset(
    {
        "turn/started",
        "turn/completed",
        "turn/finished",
        "turn/failed",
        "turn/diff/updated",
        "item/started",
        "item/updated",
        "item/completed",
        "item/agentMessage/delta",
        "item/reasoning/summaryTextDelta",
        "item/reasoning/summaryPartAdded",
        "item/reasoning/textDelta",
        "item/commandExecution/outputDelta",
        "item/commandExecution/terminalInteraction",
        "item/fileChange/outputDelta",
        "item/fileChange/patchUpdated",
        "item/mcpToolCall/progress",
        "mcpToolCall/progress",
        "command/exec/outputDelta",
        "process/outputDelta",
        "process/exited",
        "hook/started",
        "hook/completed",
    }
)
_PROGRESS_SERVER_REQUEST_METHODS = frozenset(
    {
        "item/tool/call",
        "item/tool/requestUserInput",
        "item/commandExecution/requestApproval",
        "item/fileChange/requestApproval",
        "item/permissions/requestApproval",
        "mcpServer/elicitation/request",
    }
)
_PROVIDER_ERROR_METHOD = "error"
_PROVIDER_ERROR_VARIANTS = frozenset(
    {
        "contextWindowExceeded",
        "sessionBudgetExceeded",
        "usageLimitExceeded",
        "serverOverloaded",
        "cyberPolicy",
        "internalServerError",
        "unauthorized",
        "badRequest",
        "threadRollbackFailed",
        "sandboxError",
        "other",
        "httpConnectionFailed",
        "responseStreamConnectionFailed",
        "responseStreamDisconnected",
        "responseTooManyFailedAttempts",
        "activeTurnNotSteerable",
    }
)
_PROVIDER_HTTP_VARIANTS = frozenset(
    {
        "httpConnectionFailed",
        "responseStreamConnectionFailed",
        "responseStreamDisconnected",
        "responseTooManyFailedAttempts",
    }
)
_SAFE_TURN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}")


def _codex_package_model_override(package: AgentPackage) -> tuple[str, str, str] | None:
    """Return a safe declarative package model override, when one is configured."""

    runtime = getattr(package, "runtime", None)
    codex = runtime.get("codex") if isinstance(runtime, dict) else None
    if not isinstance(codex, dict):
        return None
    values = tuple(codex.get(name) for name in ("model", "model_provider", "model_reasoning_effort"))
    if all(value is None for value in values):
        return None
    if any(
        not isinstance(value, str)
        or not value
        or any(char in value for char in '\"\r\n')
        for value in values
    ):
        raise CodexRuntimeError("Codex package model override is malformed")
    model, provider, reasoning = values
    if provider != "openai":
        raise CodexRuntimeError("Codex package model override has an unsupported provider")
    return model, provider, reasoning


def _deepseek_provider_config_lines() -> list[str]:
    """Return the secret-free Codex projection for the active DeepSeek provider."""

    return [
        f'model = "{_DEEPSEEK_MODEL}"',
        f'model_provider = "{_DEEPSEEK_PROVIDER}"',
        'model_reasoning_effort = "max"',
        "[model_providers.deepseek]",
        'name = "DeepSeek"',
        f'base_url = "{_DEEPSEEK_BASE_URL}"',
        f'env_key = "{_DEEPSEEK_API_KEY_ENV}"',
        'wire_api = "responses"',
        "[shell_environment_policy]",
        'inherit = "core"',
        f'exclude = ["{_DEEPSEEK_API_KEY_ENV}"]',
    ]


def _formal_provider_config_lines(binding: RoleModelBinding, base_url: str) -> list[str]:
    """Secret-free per-role TOML projection onto one loopback provider session.

    ``model_provider`` uses the stable runtime-local catalog provider ID, the
    provider table receives only that binding's loopback base URL plus
    ``wire_api = "responses"``, and the effort is the capability-resolved
    effective effort.  No endpoint, credential, or provider free text.  Only
    external credential-backed routes (currently ``deepseek-direct``) use this
    projection.
    """

    return [
        f'model = "{binding.model}"',
        f'model_provider = "{binding.provider_id}"',
        f'model_reasoning_effort = "{binding.effective_effort}"',
        f"[model_providers.{binding.provider_id}]",
        f'name = "{binding.provider_id}"',
        f'base_url = "{base_url}/"',
        'wire_api = "responses"',
        "[shell_environment_policy]",
        'inherit = "core"',
        'exclude = ["DEEPSEEK_API_KEY", "OPENAI_API_KEY", "LLM_API_KEY"]',
    ]


def _formal_codex_builtin_config_lines(binding: RoleModelBinding) -> list[str]:
    """Secret-free per-role TOML projection onto Codex's built-in OpenAI route.

    ``openai-codex`` keeps its catalog route identity in profiles, baselines,
    and evidence, but its per-role TOML projection must select the built-in
    provider ID ``openai``: no custom ``[model_providers.*]`` table, no base
    URL, and no environment credential key.  Authentication rides the private
    staged ChatGPT login cache, never an API key.
    """

    return [
        f'model = "{binding.model}"',
        f'model_provider = "{CODEX_TOML_PROVIDER_ID}"',
        f'model_reasoning_effort = "{binding.effective_effort}"',
        "[shell_environment_policy]",
        'inherit = "core"',
        'exclude = ["DEEPSEEK_API_KEY", "OPENAI_API_KEY", "LLM_API_KEY"]',
    ]


_PROXY_ENV_KEYS = (
    "http_proxy",
    "https_proxy",
    "no_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
)

# R3.0-011 v3 read-bridge mode: the child-local read_proxy_mcp bridge selects it
# from PLATFORM_PROXY_MODE.  In this mode the bridge forwards only the invariant
# batch ticket and passes the proxy's exact tool schemas through; every
# per-Ontology scope value stays Host-owned (see ScopedReadProxy._v3_scope_arguments).
_V3_PROXY_BRIDGE_MODE = "v3-acceptance"


def _minimal_codex_process_env(home: Path, api_key: str | None = None) -> dict[str, str]:
    """Build the explicit environment allowed for a Codex app-server process."""

    values = {
        "CODEX_HOME": str(home),
        "HOME": str(home),
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "TERM": "xterm-256color",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }
    # Forward the Host's outbound proxy configuration only.  This host reaches
    # chatgpt.com exclusively through a local proxy, while Codex 0.147.0's
    # ``outbound_proxy_policy: ReqwestDefault`` otherwise connects directly and
    # every sampling/analytics/models request times out at the network layer
    # (R2.3-008 start5).  ``no_proxy`` must travel with the proxy variables so
    # in-namespace loopback targets (platform backend 127.0.0.1:8001, database
    # localhost:5434) stay direct.  Only forward what the Host actually sets.
    for key in _PROXY_ENV_KEYS:
        value = os.environ.get(key)
        if value:
            values[key] = value
    if api_key is not None:
        values[_DEEPSEEK_API_KEY_ENV] = api_key
    return values


def audit_private_artifacts(
    roots: Path | list[Path] | tuple[Path, ...],
    secret_values: list[bytes] | tuple[bytes, ...] = (),
    *,
    process_surfaces: list[tuple[str, bytes | None]]
    | tuple[tuple[str, bytes | None], ...] = (),
) -> dict[str, Any]:
    """Scan private generated artifacts for secret bytes without returning content.

    The result is intentionally limited to counts and secret digests.  Regular
    files are scanned recursively, including SQLite ``-wal``/``-shm`` siblings;
    sockets, symlinks, and device files are ignored.  ``process_surfaces`` lets
    cleanup inspect argv/environment snapshots before a process is terminated.
    """

    if isinstance(roots, Path):
        root_values = [roots]
    else:
        root_values = list(roots)
    values = tuple(
        value
        for value in secret_values
        if isinstance(value, bytes) and value
    )
    # Preserve order while deduplicating exact bytes; digest values are safe to
    # expose in cleanup evidence and make repeated audits deterministic.
    unique_values: list[bytes] = []
    seen: set[bytes] = set()
    for value in values:
        if value not in seen:
            unique_values.append(value)
            seen.add(value)
    digests = tuple(hashlib.sha256(value).hexdigest() for value in unique_values)
    matched_surfaces: set[str] = set()
    matched_digest_indices: set[int] = set()
    scanned_files = 0
    scan_error_count = 0
    scan_complete = True

    def inspect(surface: str, payload: bytes) -> None:
        for index, value in enumerate(unique_values):
            if value in payload:
                matched_surfaces.add(surface)
                matched_digest_indices.add(index)

    for root in root_values:
        try:
            path = Path(root)
            if path.is_file():
                candidates = [path]
            elif path.is_dir():
                candidates = list(path.rglob("*"))
            else:
                # A missing root is an empty, already-clean surface.  It is not
                # an I/O failure; an OSError raised while inspecting it is.
                candidates = []
        except OSError:
            scan_error_count += 1
            scan_complete = False
            continue
        for candidate in candidates:
            try:
                metadata = candidate.lstat()
            except OSError:
                scan_error_count += 1
                scan_complete = False
                continue
            if not stat.S_ISREG(metadata.st_mode):
                continue
            # Keep the walk generic, but avoid loading arbitrary binary blobs or
            # generated model payloads that cannot contain textual auth material.
            shell_snapshot = any(parent.name == "shell_snapshots" for parent in candidate.parents)
            if (
                candidate.suffix.lower() not in _SECRET_AUDIT_SUFFIXES
                and not candidate.name.endswith(("-wal", "-shm"))
                and candidate.name not in {
                    "auth.json",
                    "config.toml",
                    "environ",
                    "cmdline",
                }
                and not shell_snapshot
            ):
                continue
            try:
                payload = candidate.read_bytes()
            except OSError:
                scan_error_count += 1
                scan_complete = False
                continue
            scanned_files += 1
            inspect(str(candidate), payload)
    for surface, payload in process_surfaces:
        if not isinstance(surface, str):
            continue
        if isinstance(payload, bytes):
            inspect(surface, payload)
        else:
            # ``None`` is the internal marker for a live process surface that
            # could not be read.  Treat it as an audit failure without retaining
            # the path or any process contents in the result.
            scan_error_count += 1
            scan_complete = False
    return {
        "scanned_files": scanned_files,
        "match_count": len(matched_surfaces),
        "matched_secret_count": len(matched_digest_indices),
        "matched_secret_digests": [
            digests[index] for index in sorted(matched_digest_indices)
        ],
        "matched_surfaces": sorted(matched_surfaces),
        "scan_complete": scan_complete,
        "scan_error_count": scan_error_count,
    }


def _auth_secret_leaf_values(payload: bytes) -> tuple[bytes, ...]:
    """Extract sensitive scalar leaves from a provider auth JSON document.

    App-server logs and SQLite journals may retain only a token value rather than the
    original JSON object.  Keep exact sensitive leaves in the adapter's transient audit
    set so cleanup catches that representation too, while ignoring ordinary metadata
    such as IDs, labels, URLs, and expiry values.
    """

    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ()
    values: list[bytes] = []

    def normalized_key(value: str) -> str:
        value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
        return value.casefold().replace("-", "_")

    def sensitive_key(value: object) -> bool:
        if not isinstance(value, str):
            return False
        normalized = normalized_key(value)
        return normalized in _AUTH_SECRET_KEY_NAMES or normalized.endswith(
            ("_token", "_secret", "_api_key", "_private_key")
        )

    def visit(value: object, key: object = None) -> None:
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                visit(child_value, child_key)
            return
        if isinstance(value, list):
            for child_value in value:
                visit(child_value, key)
            return
        if not sensitive_key(key) or not isinstance(value, str) or not value.strip():
            return
        encoded = value.encode("utf-8")
        if encoded not in values:
            values.append(encoded)

    visit(document)
    return tuple(values)


class _StderrDrain:
    """Bounded, non-blocking stderr consumer with split-sentinel detection."""

    def __init__(
        self,
        stream: Any,
        secret_supplier: Callable[[], tuple[bytes, ...]],
        on_match: Callable[[], None],
    ) -> None:
        self.stream = stream
        self.secret_supplier = secret_supplier
        self.on_match = on_match
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.bytes_drained = 0
        self.match_count = 0
        self.lifecycle_failure = False
        self._lock = threading.Lock()

    def start(self) -> None:
        if self.thread is not None:
            return
        self.thread = threading.Thread(
            target=self._run,
            name="formal-stderr-drain",
            daemon=True,
        )
        self.thread.start()

    @staticmethod
    def _bytes(value: Any) -> bytes:
        if isinstance(value, bytes):
            return value
        if isinstance(value, str):
            return value.encode("utf-8", "replace")
        return b""

    def _run(self) -> None:
        # Retain only the largest sentinel-sized tail between reads; stderr is
        # drained continuously and never accumulated as evidence.
        tail = b""
        try:
            while not self.stop_event.is_set():
                read = getattr(self.stream, "read", None)
                binary_stream = getattr(self.stream, "buffer", None)
                read1 = getattr(binary_stream, "read1", None)
                if callable(read1):
                    chunk = self._bytes(read1(4096))
                elif not callable(read):
                    raise OSError("stderr stream is unavailable")
                else:
                    chunk = self._bytes(read(4096))
                if not chunk:
                    return
                with self._lock:
                    self.bytes_drained += len(chunk)
                window = tail + chunk
                matched = False
                for secret in self.secret_supplier():
                    if secret and secret in window:
                        matched = True
                        break
                if matched:
                    with self._lock:
                        self.match_count += 1
                    try:
                        self.on_match()
                    except Exception:
                        pass
                tail = window[-4095:]
        except Exception:
            if not self.stop_event.is_set():
                self.lifecycle_failure = True

    def stop(self) -> None:
        self.stop_event.set()
        thread = self.thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)

    def snapshot(self) -> dict[str, int | bool]:
        with self._lock:
            return {
                "bytes_drained": self.bytes_drained,
                "match_count": self.match_count,
                "lifecycle_failure": self.lifecycle_failure,
            }


@dataclass
class _Agent:
    agent_id: str
    package: AgentPackage
    home: Path
    work: Path
    skills: Path
    process: subprocess.Popen[str] | None = None
    thread_id: str | None = None
    active_turn_id: str | None = None
    last_started_turn_id: str | None = None
    last_completed_turn_id: str | None = None
    state: str = "starting"
    request_id: int = 0
    first_turn_input: list[dict[str, Any]] = field(default_factory=list)
    stdout_buffer: bytes = b""
    dynamic_tool_calls: int = 0
    message_deltas: dict[str, list[str]] = field(default_factory=dict)
    completed_message_ids: set[str] = field(default_factory=set)
    platform_tools: frozenset[str] = field(default_factory=frozenset)
    app_server_host_pid: int | None = None
    mechanics_contract_path: Path | None = None
    retrieval_mcp_path: Path | None = None
    retrieval_verifier_path: Path | None = None
    proof_v2_path: Path | None = None
    retrieval_asset_fds: tuple[int, ...] = ()
    auth_path: Path | None = None
    auth_barrier_pending: bool = False
    auth_unlinked_monotonic: float | None = None
    credential_mode: str = "file_auth"
    provider_proxy_ready_monotonic: float | None = None
    stderr_drain: _StderrDrain | None = None
    first_dispatch_monotonic: float | None = None
    schema_version: int = 1
    proof_gate: bool = False
    fallback_eligible: bool = False
    retrieval_episode: int = 0
    retrieval_state: str = "idle"
    completed_mcp_item_ids: set[str] = field(default_factory=set)
    io_lock: threading.RLock = field(default_factory=threading.RLock)
    state_lock: threading.RLock = field(default_factory=threading.RLock)
    # Monotonic timestamp of the last App Server notification observed for this role.
    # Refreshed by ``_notification`` on every stdout line; read by the inactivity
    # watchdog thread to detect a hung model endpoint without blocking the main loop.
    last_output_monotonic: float = 0.0
    inactivity_watchdog_thread: threading.Thread | None = None
    inactivity_watchdog_stop: threading.Event = field(default_factory=threading.Event)
    inactivity_failure: dict[str, Any] | None = None
    # Adapter-owned typed runtime failure latch.  Provider errors and inactivity
    # watchdogs share this boundary so a secondary EOF/reader exception cannot
    # overwrite the first sanitized infrastructure cause.
    runtime_failure: dict[str, Any] | None = None
    runtime_failure_termination_attempted: bool = False


def _v3_child_teardown_evidence(
    resource: Any,
    *,
    proxy: Any,
    report_sink: Any,
    private_root: str,
    socket_root: str,
    sink_thread: Any = None,
) -> dict[str, Any]:
    """Observe one v3 child's actual teardown outcome (R3.0-011).

    Every value is read from post-``destroy`` state -- the stopped servers, the
    removed private tree and socket root -- so the carrier records what really
    happened to the resources it allocated instead of assuming success.  The
    shared legacy ``destroy``/``stop`` pair is untouched: only this v3 boundary
    observes it, and an unrelated concurrently running child can never appear
    in this evidence.
    """

    def _stopped(target: Any) -> bool:
        return target is None or not bool(getattr(target, "active", True))

    def _sink_stopped(sink: Any) -> bool:
        """Observe the real ``ReportSinkServer`` shutdown instead of guessing.

        The sink defines no ``active`` property, so the generic probe above
        reads every real sink as still running even after a successful
        ``stop()``.  A sink is still live exactly while its serve loop runs,
        its listening socket exists or its socket file does; the serve thread
        handle is the pre-``destroy`` capture, because ``stop()`` clears
        ``_thread`` and would make a post-hoc liveness check vacuous.  A sink
        that never started owns none of those, so nothing of it is live.
        """

        if sink is None:
            return True
        if isinstance(sink_thread, threading.Thread) and sink_thread.is_alive():
            return False
        if getattr(sink, "_server", None) is not None:
            return False
        socket_path = getattr(sink, "socket_path", None)
        if isinstance(socket_path, (str, Path)) and str(socket_path) and Path(socket_path).exists():
            return False
        return True

    def _removed(path: str) -> bool:
        # An empty path means this child never owned that resource; it is
        # trivially gone and must not read as a teardown failure.
        return not path or not Path(path).exists()

    return {
        "child_stopped": bool(getattr(resource, "stopped", False)),
        "child_destroyed": bool(getattr(resource, "destroyed", False)),
        "report_sink_stopped": _sink_stopped(report_sink),
        "proxy_stopped": _stopped(proxy),
        "private_root_removed": _removed(private_root),
        "socket_root_removed": _removed(socket_root),
    }


class _CodexChildResource:
    """Runner-owned private Examiner process/session resource.

    The adapter's explicit ``acceptance_child_factory`` remains a deterministic test seam.
    Production calls construct this resource with a real private Codex process, a private
    report sink, and (for Platform) a ticket-bound read proxy.  No child identifier or
    credential is exposed through the Acceptance carrier's opaque handle.
    """

    def __init__(
        self,
        spec: dict[str, Any],
        process: Any | None = None,
        *,
        proxy: ScopedReadProxy | None = None,
        report_sink: ReportSinkServer | None = None,
        thread_id: str | None = None,
        first_turn_input: list[dict[str, Any]] | None = None,
        startup_complete: bool = True,
    ):
        self.spec = dict(spec)
        self.process = process
        self.proxy = proxy
        self.report_sink = report_sink
        self.thread_id = thread_id
        self.first_turn_input = list(first_turn_input or [])
        self.submitted_reports: list[Mapping[str, Any]] = []
        self.terminal_event = False
        self.stopped = False
        self.destroyed = False
        self._stopping = False
        self.failure_category: str | None = None
        self.failure_reason: str | None = None
        self.infrastructure_failure: Any | None = None
        self._failure_recorded = False
        terminal_state = self.spec.get("_terminal_state")
        self._carrier_terminal = isinstance(terminal_state, dict) and hasattr(
            terminal_state.get("lock"), "__enter__"
        )
        if self._carrier_terminal:
            self._terminal_state = terminal_state
            self._terminal_lock = terminal_state["lock"]
        else:
            self._terminal_state = {"lock": threading.RLock(), "winner": None}
            self._terminal_lock = self._terminal_state["lock"]
        self.startup_complete = startup_complete
        self._watchdog_stop = threading.Event()
        self._watchdog_thread: threading.Thread | None = None
        # The Examiner stdout pump owns the child App Server output after
        # ``turn/start`` returns; it is lifecycle-bound to this resource and is
        # stopped/joined before any descriptor teardown in ``stop``.
        self._pump_stop = threading.Event()
        self._stdout_pump: threading.Thread | None = None
        self._pump_started = False
        self._output_pump_deferred = bool(self.spec.get("defer_output_pump"))
        self._child_agent: _Agent | None = None
        self._adapter: CodexRuntimeAdapter | None = None
        self._read_key_revoked = False
        if process is not None:
            self._start_watchdog()

    def _start_watchdog(self) -> None:
        timeout_value = self.spec.get("timeout_seconds", 60)
        try:
            timeout = float(timeout_value)
        except (TypeError, ValueError):
            timeout = 60.0
        timeout = max(0.01, min(timeout, 24 * 60 * 60))

        def watch() -> None:
            deadline = time.monotonic() + timeout
            while not self._watchdog_stop.wait(0.05):
                process = self.process
                poll = getattr(process, "poll", None)
                if callable(poll):
                    try:
                        returncode = poll()
                    except Exception:
                        returncode = None
                    if returncode is not None:
                        if not self.stopped and not self.destroyed and returncode != 0:
                            self._record_failure(
                                "runtime",
                                "child-crash" if self.startup_complete else "child-start-failed",
                            )
                        return
                if time.monotonic() >= deadline:
                    failure_won = self._record_failure(
                        "runtime",
                        "child-timeout" if self.startup_complete else "child-start-failed",
                    )
                    if failure_won:
                        self._terminate_process(grace_seconds=0.5)
                    return

        thread = threading.Thread(target=watch, name="acceptance-child-watchdog", daemon=True)
        self._watchdog_thread = thread
        thread.start()

    def start_stdout_pump(self, adapter: CodexRuntimeAdapter, agent: _Agent) -> None:
        """Start the lifecycle-owned Examiner App Server stdout pump.

        Reuses the existing ``_read_output_line`` and the child ``_Agent``'s
        reentrant ``io_lock`` so every reader serializes on the same lock
        ``_rpc_locked`` already honors.  Each parsed notification is dispatched
        through ``adapter._notification``; no new read path is introduced.
        """

        with self._terminal_lock:
            if self._pump_started or self.stopped or self.destroyed:
                return
            self._adapter = adapter
            self._child_agent = agent
            self._pump_started = True
        thread = threading.Thread(
            target=self._run_stdout_pump,
            name="acceptance-child-stdout-pump",
            daemon=True,
        )
        self._stdout_pump = thread
        thread.start()

    def activate_output_pump(self) -> None:
        """Activate a formal pump after the carrier has registered the resource."""

        if not self._output_pump_deferred:
            return
        adapter = self._adapter
        agent = self._child_agent
        if adapter is None or agent is None:
            raise CodexRuntimeError("deferred Examiner output pump is unbound")
        self.start_stdout_pump(adapter, agent)

    def _run_stdout_pump(self) -> None:
        adapter = self._adapter
        agent = self._child_agent
        if adapter is None or agent is None:
            return
        while not self._pump_stop.is_set():
            try:
                with agent.io_lock:
                    if self._pump_stop.is_set():
                        return
                    line = adapter._read_output_line(agent, 0.1)
                    if line is None:
                        continue
                    try:
                        value = json.loads(line)
                    except json.JSONDecodeError:
                        # A stop requested at the very start of ``stop`` (via
                        # ``_watchdog_stop``) precedes descriptor teardown, so an
                        # output close during teardown is not a failure.
                        if not self._watchdog_stop.is_set():
                            self._record_failure("runtime", "child-output-malformed")
                        return
                    metrics = getattr(self, "metrics", None)
                    if metrics is not None:
                        try:
                            metrics.observe_notification(value)
                        except ExaminerRuntimeBlocked as blocked:
                            self.blocked = blocked
                            self._record_failure("runtime", blocked.reason)
                            self._terminate_process(grace_seconds=0.5)
                            return
                        if value.get("method") in {"turn/completed", "turn/finished"}:
                            self.terminal_event = bool(metrics.terminal_event)
                    elif value.get("method") in {"turn/completed", "turn/finished"}:
                        self.terminal_event = True
                    # Lean Examiner output is a typed-report runtime surface.  Do
                    # not leak model-message deltas/completions into the generic
                    # adapter message accumulator; lifecycle, provider-error, and
                    # terminal notifications still use the established dispatcher.
                    method = value.get("method")
                    params = value.get("params")
                    item = params.get("item") if isinstance(params, Mapping) else None
                    lean_message = (
                        bool(self.spec.get("lean_examiner"))
                        and isinstance(method, str)
                        and (
                            method.startswith("item/agentMessage/")
                            or (
                                method in {"item/completed", "item/updated"}
                                and isinstance(item, Mapping)
                                and item.get("type") == "agentMessage"
                            )
                        )
                    )
                    if lean_message:
                        # Lean output stays outside the generic message
                        # accumulator, but Acceptance text-verdict recovery needs
                        # raw agent-message and reasoning text.  Record streaming
                        # deltas and full completed-message text under stable
                        # item IDs; completed messages are still not promoted to
                        # ``_messages``.
                        if method in {
                            "item/agentMessage/delta",
                            "item/reasoning/textDelta",
                            "item/reasoning/summaryTextDelta",
                        }:
                            item_id = params.get("itemId")
                            delta = params.get("delta")
                            if isinstance(item_id, str) and isinstance(delta, str):
                                agent.message_deltas.setdefault(item_id, []).append(delta)
                        elif method in {"item/completed", "item/updated"} and isinstance(item, Mapping):
                            item_id = item.get("id")
                            text = item.get("text")
                            if isinstance(item_id, str) and isinstance(text, str) and text:
                                agent.message_deltas.setdefault(item_id, []).append(text)
                    else:
                        adapter._notification(agent, value)
                    if getattr(agent, "runtime_failure", None) is not None:
                        return
            except CodexRuntimeError:
                if not self._watchdog_stop.is_set() and getattr(agent, "runtime_failure", None) is None:
                    self._record_failure("runtime", "child-output-closed")
                return
            except Exception:
                if not self._watchdog_stop.is_set() and getattr(agent, "runtime_failure", None) is None:
                    self._record_failure("runtime", "child-output-failed")
                return

    def failure_evidence(self) -> dict[str, str] | None:
        """Return only fixed sanitized infrastructure codes for the carrier."""
        if not self.failure_category or not self.failure_reason:
            return None
        evidence: dict[str, Any] = {
            "failure_category": self.failure_category,
            "reason_code": self.failure_reason,
        }
        sink = self.report_sink
        rejections = getattr(sink, "_rejections", None)
        if isinstance(rejections, (list, tuple)):
            evidence["report_sink_rejections"] = len(rejections)
        return evidence

    def _record_failure(self, category: str, reason: str) -> bool:
        """Attempt one terminal infrastructure failure; return whether it won."""

        with self._terminal_lock:
            if self._failure_recorded or self.stopped or self.destroyed or self._stopping:
                return False
            if self._terminal_state.get("winner") == "report":
                return False
            callback = self.spec.get("record_infrastructure_failure")
            if callable(callback):
                try:
                    recorded = callback(category, reason)
                except Exception:
                    # Callback failures are runtime failures in their own right:
                    # retain only the fixed local code, latch the adapter's typed
                    # failure queue, and terminate the child.  Never retain raw
                    # exception text from a carrier/test seam.
                    self.failure_category = category
                    self.failure_reason = reason
                    self._failure_recorded = True
                    self._terminal_state["winner"] = "failure"
                    adapter = self._adapter
                    agent = self._child_agent
                    if adapter is not None and agent is not None:
                        try:
                            adapter._latch_runtime_failure(
                                agent,
                                {"source": "child-resource", "reason": "failure-callback-error"},
                            )
                        except Exception:
                            pass
                    self._terminate_process(grace_seconds=0.5)
                    return True
                if recorded is None and self._carrier_terminal:
                    # The carrier reports a terminal report winner (or a
                    # cleanup/recycle conflict).  Do not turn that late callback
                    # into a second failure or kill the already reported child.
                    return False
                self.infrastructure_failure = recorded
            self.failure_category = category
            self.failure_reason = reason
            self._failure_recorded = True
            self._terminal_state["winner"] = "failure"
            return True

    def _terminate_process(self, *, grace_seconds: float = 5.0) -> None:
        process = self.process
        if process is None:
            return
        try:
            running = getattr(process, "poll", lambda: None)() is None
        except Exception:
            running = True
        if not running:
            return
        pid = getattr(process, "pid", None)
        try:
            if isinstance(pid, int) and pid > 0:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            else:
                terminate = getattr(process, "terminate", None)
                if callable(terminate):
                    terminate()
        except (ProcessLookupError, PermissionError, OSError):
            terminate = getattr(process, "terminate", None)
            if callable(terminate):
                terminate()
        wait = getattr(process, "wait", None)
        if callable(wait):
            try:
                wait(timeout=grace_seconds)
                return
            except (subprocess.TimeoutExpired, TypeError):
                pass
        try:
            if isinstance(pid, int) and pid > 0:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            else:
                kill = getattr(process, "kill", None)
                if callable(kill):
                    kill()
        except (ProcessLookupError, PermissionError, OSError):
            kill = getattr(process, "kill", None)
            if callable(kill):
                kill()
        if callable(wait):
            try:
                wait(timeout=grace_seconds)
            except (subprocess.TimeoutExpired, TypeError):
                pass

    def stop(self) -> None:
        # Signal both lifecycle threads before any descriptor teardown so the pump
        # never reads a closed stdout and a join-timeout EOF cannot misfire as a
        # failure.  ``_watchdog_stop`` is the earliest stop signal (set here at the
        # very start of ``stop``); ``self.stopped`` is only the final state below.
        with self._terminal_lock:
            self._stopping = True
            self._watchdog_stop.set()
            self._pump_stop.set()
        pump = self._stdout_pump
        if pump is not None:
            pump.join(timeout=2.0)
        watchdog = self._watchdog_thread
        if watchdog is not None:
            watchdog.join(timeout=2.0)
        self._terminate_process()
        if self._child_agent is not None and self._child_agent.stderr_drain is not None:
            self._child_agent.stderr_drain.stop()
            if self._adapter is not None:
                self._adapter._stderr_drain_reports[self._child_agent.agent_id] = (
                    self._child_agent.stderr_drain.snapshot()
                )
                if self._child_agent.stderr_drain.lifecycle_failure:
                    self._adapter._stderr_drain_failures[self._child_agent.agent_id] = {
                        "category": "runtime/infrastructure",
                        "reason_code": "stderr-drain-failed",
                    }
        if self.proxy is not None:
            self.proxy.revoke()
            self.proxy.stop()
        if self.report_sink is not None:
            self.report_sink.stop()
        revoke = self.spec.get("read_key_revoke")
        key_id = self.spec.get("read_key_id")
        if callable(revoke) and isinstance(key_id, str) and not self._read_key_revoked:
            try:
                revoke(key_id)
            finally:
                self._read_key_revoked = True
        self.spec.pop("read_key_plaintext", None)
        self.spec.pop("report_submit", None)
        self.spec.pop("report_submit_payload", None)
        self.spec.pop("platform_forwarder", None)
        self.spec.pop("_runtime_proxy", None)
        self.spec.pop("_runtime_report_sink", None)
        self.stopped = True

    def _retain_child_session(self) -> None:
        """Copy the child Codex session rollout into run evidence before teardown.

        R2.3-009 (2026-08-20): the operator explicitly authorized retaining full
        Examiner child session content in evidence, overriding the historical
        destroy-without-trace rule, so live child-timeouts can be diagnosed from
        the child's own conversation afterwards.  Credentials (auth cache,
        proxy/report token files, key material) are still excluded: they are not
        session content and serve no diagnosis.
        """

        agent = self._child_agent
        run_root = getattr(self._adapter, "_run_root", None) if self._adapter is not None else None
        if agent is None or not isinstance(run_root, Path):
            return
        target_root = run_root / "evidence" / "child-sessions"
        sessions = Path(agent.home) / "sessions"
        if sessions.is_dir() and not sessions.is_symlink():
            target_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            target = target_root / agent.agent_id
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(sessions, target)
        for name in ("config.toml", "child-config.json", "examiner-descriptor.json", "input.json"):
            source = Path(agent.home) / name
            if source.is_file() and not source.is_symlink():
                target_root.mkdir(parents=True, exist_ok=True, mode=0o700)
                shutil.copy2(source, target_root / f"{agent.agent_id}.{name}")

    def destroy(self) -> None:
        self.stop()
        try:
            self._retain_child_session()
        except OSError:
            # Retention is best-effort diagnosis support; it must never block
            # the mandatory credential teardown below.
            pass
        private_root = self.spec.get("private_root")
        if isinstance(private_root, str) and private_root:
            path = Path(private_root)
            if path.is_symlink():
                raise CodexRuntimeError("child private input tree is a symlink")
            if path.exists() and path.is_dir():
                shutil.rmtree(path)
        socket_root = self.spec.get("_runtime_socket_root")
        if isinstance(socket_root, str) and socket_root:
            path = Path(socket_root)
            if not path.is_symlink() and path.exists() and path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
        # Do not retain key plaintext or untrusted child output in the adapter object.
        self.spec.pop("read_key_plaintext", None)
        self.spec.pop("read_key_revoke", None)
        self.spec.pop("report_submit", None)
        self.spec.pop("record_infrastructure_failure", None)
        self.spec.pop("platform_forwarder", None)
        self.spec.pop("_packet", None)
        self.spec.pop("_metrics", None)
        self.spec.pop("first_turn_input", None)
        self.spec.pop("_submitted_reports", None)
        self.spec.pop("_runtime_socket_root", None)
        self.submitted_reports.clear()
        registry_remove = self.spec.get("_registry_remove")
        handle_digest = self.spec.get("child_handle_digest")
        if callable(registry_remove) and isinstance(handle_digest, str):
            registry_remove(handle_digest)
        self.spec.pop("_registry_remove", None)
        self.destroyed = True


class CodexRuntimeAdapter(RuntimeAdapter):
    """One app-server process and persistent Codex Thread per frozen Agent."""

    def __init__(
        self,
        *,
        repository_root: Path,
        codex_binary: str = "codex",
        use_bwrap: bool = True,
        process_factory: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
        acceptance_child_factory: Callable[[dict[str, Any]], Any] | None = None,
    ):
        self.root, self.use_bwrap, self.process_factory = (
            repository_root,
            use_bwrap,
            process_factory,
        )
        resolved = shutil.which(codex_binary)
        if resolved is None:
            for candidate in (
                Path.home() / ".codex" / "packages" / "standalone" / "current" / "bin" / "codex",
                Path.home() / ".codex" / "packages" / "standalone" / "current" / "codex",
            ):
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    resolved = str(candidate)
                    break
        if resolved is None and (Path(codex_binary).is_absolute() or "/" in codex_binary):
            resolved = codex_binary
        self.codex_binary = resolved or codex_binary
        self._acceptance_child_factory = acceptance_child_factory
        self._acceptance_children: dict[str, Any] = {}
        self.agents: dict[str, _Agent] = {}
        self._messages: list[RuntimeMessage] = []
        self._run_root: Path | None = None
        self._run_id: str | None = None
        self._active_run: Any | None = None
        self._acceptance: Any | None = None
        self._coordination_enabled = False
        self._candidate_platform_gate_enabled = False
        self._staged_decisions_enabled = False
        # R3.0-009 unified semantic graph mode; set per run next to the staged
        # flag so the bind table and the Runner schema dispatch agree.
        self._unified_graph = False
        self._formal_turn_binding_required = False
        self._team_model_profile: TeamModelProfile | None = None
        self._private_credentials_destroyed: dict[str, bool] = {}
        self._secret_audit_values: list[bytes] = []
        self._secret_audit_failures: dict[str, dict[str, Any]] = {}
        self._child_auth_barriers: dict[str, dict[str, float | None]] = {}
        self._inactivity_timeout_seconds = _LLM_INACTIVITY_TIMEOUT_SECONDS
        self._inactivity_failures: list[tuple[str, dict[str, Any]]] = []
        self._inactivity_lock = threading.Lock()
        self._runtime_failures: list[tuple[str, dict[str, Any]]] = []
        self._runtime_failure_lock = threading.Lock()
        self._provider_sessions: ProviderSessionManager | None = None
        self._stderr_drain_failures: dict[str, dict[str, Any]] = {}
        self._stderr_drain_reports: dict[str, dict[str, int | bool]] = {}
        self._provider_session_failure_latched = False
        # Cleanup is a lifecycle boundary, not a best-effort recomputation.  The
        # lock serializes stop/cleanup callers and the snapshot makes repeated
        # evidence reads immutable even if a caller mutates a returned dict or a
        # private tree is recreated after teardown.
        self._cleanup_lock = threading.RLock()
        self._cleanup_snapshot: dict[str, Any] | None = None
        self._cleanup_errors: dict[str, dict[str, str]] = {}
        self._formal_cleanup_aggregate: dict[str, Any] | None = None
        self._provider_stop_status: dict[str, dict[str, bool | int]] = {}

    def _validated_model_override(
        self,
        package: AgentPackage,
        *,
        formal: bool,
    ) -> tuple[str, str, str] | RoleModelBinding | None:
        """Resolve a package model from the frozen formal profile when required."""

        if formal:
            return self._validated_formal_role_binding(package.package_id)
        return _codex_package_model_override(package)

    def _validated_formal_role_binding(self, package_id: str) -> RoleModelBinding:
        """Resolve one exact formal role binding from the frozen profile.

        ``TeamRunner.prepare`` validates the on-disk profile and freezes its digest
        before any Runtime starts.  Keep this second, Runtime-local guard because
        thread/start is the last boundary before a model process can execute: a
        missing package binding or an in-memory binding drift must fail closed
        rather than silently falling back to a package default or a host model.
        The lookup key is always the canonical package ID; Source and Platform
        Examiner packages both declare role ``source-specialist`` and would
        collide if ``AgentPackage.role`` were used here.
        """

        if package_id not in MODEL_PROFILE_PACKAGE_IDS:
            raise CodexRuntimeError("formal model profile package binding is invalid")
        profile = self._team_model_profile
        if profile is None:
            raise CodexRuntimeError("formal runtime is missing its validated model profile")
        try:
            binding = profile.binding_for(package_id)
        except Exception as exc:
            raise CodexRuntimeError("formal model profile package binding is invalid") from exc
        route = PROVIDER_CATALOG.get(binding.provider_id)
        if (
            route is None
            or binding.model not in route.models
            or binding.requested_effort not in REQUESTED_EFFORT_TIERS
            or binding.effective_effort not in REQUESTED_EFFORT_TIERS
            or route.effective_effort(binding.requested_effort) != binding.effective_effort
        ):
            raise CodexRuntimeError("formal model profile binding drifted")
        return binding

    def _remember_secret(self, value: object) -> None:
        """Retain only transient credential bytes needed by the cleanup audit.

        Provider auth is JSON, so remember both the raw document and its sensitive
        scalar leaves.  The latter catches app-server logs that persist only a token
        value.  No value is returned in cleanup evidence and the list is cleared at
        the lifecycle boundary.
        """

        if isinstance(value, str):
            value = value.encode("utf-8")
        if not isinstance(value, bytes) or not value:
            return
        for candidate in (value, *_auth_secret_leaf_values(value)):
            if candidate and candidate not in self._secret_audit_values:
                self._secret_audit_values.append(candidate)

    def _secret_values_for_audit(self) -> tuple[bytes, ...]:
        values = list(self._secret_audit_values)
        sessions = self._provider_sessions
        if sessions is not None:
            values.extend(sessions.secret_values())
        return tuple(values)

    def _on_stderr_secret_match(self, agent: _Agent) -> None:
        self._stderr_drain_failures[agent.agent_id] = {
            "category": "runtime/infrastructure",
            "reason_code": "provider-secret-on-stderr",
        }

    def _on_provider_session_failure(self, reason_code: str) -> None:
        # The session callback carries only a fixed local reason code; provider
        # status/text never enters the Runtime failure queue.  The latch keeps
        # the first provider failure authoritative: a later cleanup failure
        # cannot overwrite it.
        if self._provider_session_failure_latched:
            return
        self._provider_session_failure_latched = True
        with self._runtime_failure_lock:
            self._runtime_failures.append(
                (
                    "provider-sessions",
                    {
                        "category": "runtime/infrastructure",
                        "reason_code": reason_code
                        if isinstance(reason_code, str)
                        and reason_code
                        in {
                            "provider-upstream-failed",
                            "provider-session-cleanup-failed",
                        }
                        else "provider-upstream-failed",
                    },
                )
            )

    def _start_stderr_drain(self, agent: _Agent) -> None:
        process = agent.process
        stream = getattr(process, "stderr", None) if process is not None else None
        if stream is None:
            return
        drain = _StderrDrain(
            stream,
            self._secret_values_for_audit,
            lambda: self._on_stderr_secret_match(agent),
        )
        agent.stderr_drain = drain
        drain.start()

    @staticmethod
    def _read_secret_bytes(path: Path) -> bytes | None:
        try:
            value = path.read_bytes()
        except OSError:
            return None
        return value if value else None

    @staticmethod
    def _stage_private_auth(source: Path, target: Path) -> None:
        """Stage provider auth through one no-follow, exclusive, fsynced copy."""

        occupied = target.exists() or target.is_symlink()
        if occupied:
            raise CodexRuntimeError("private provider auth destination is occupied")
        try:
            _copy_private(source, target, 0o600)
        except Exception as exc:
            # The private-copy primitive removes a partial destination on write
            # failure. Keep the Runtime surface typed and never expose source
            # paths or credential bytes through the exception text.
            if not occupied:
                target.unlink(missing_ok=True)
            raise CodexRuntimeError("private provider auth staging failed") from exc

    def _audit_process_surfaces(
        self,
        agent: _Agent,
        *,
        secret_values: tuple[bytes, ...] | None = None,
    ) -> dict[str, Any]:
        return audit_private_artifacts(
            (),
            self._secret_values_for_audit() if secret_values is None else secret_values,
            process_surfaces=self._process_surface_payloads(agent),
        )

    @staticmethod
    def _process_surface_payloads(agent: _Agent) -> list[tuple[str, bytes | None]]:
        """Capture process argv/env and live ``/proc`` surfaces without secrets."""

        surfaces: list[tuple[str, bytes | None]] = []
        process = agent.process
        if process is not None:
            command = getattr(process, "args", None)
            if command is None:
                command = getattr(process, "command", None)
            if isinstance(command, (list, tuple)):
                surfaces.append((f"{agent.agent_id}:argv", " ".join(map(str, command)).encode()))
            elif isinstance(command, str):
                surfaces.append((f"{agent.agent_id}:argv", command.encode()))
            environment = getattr(process, "env", None)
            if not isinstance(environment, dict):
                process_kwargs = getattr(process, "kwargs", None)
                if isinstance(process_kwargs, dict):
                    environment = process_kwargs.get("env")
            if isinstance(environment, dict):
                surfaces.append(
                    (
                        f"{agent.agent_id}:env",
                        "\0".join(f"{key}={value}" for key, value in environment.items()).encode(),
                    )
                )
            pid = getattr(process, "pid", None)
            if isinstance(pid, int) and pid > 0:
                poll = getattr(process, "poll", None)
                try:
                    process_alive = bool(poll() is None) if callable(poll) else True
                except Exception:
                    process_alive = True
                for name in ("cmdline", "environ"):
                    try:
                        surfaces.append((f"{agent.agent_id}:{name}", Path(f"/proc/{pid}/{name}").read_bytes()))
                    except OSError:
                        # A dead process naturally loses its /proc surface.  A
                        # live process whose surface disappears is an audit
                        # failure and must make the formal aggregate fail closed.
                        if process_alive:
                            surfaces.append((f"{agent.agent_id}:{name}", None))
        return surfaces

    def _record_cleanup_audit(
        self,
        identity: str,
        result: dict[str, Any],
        *,
        ignore_auth_paths: bool = False,
        suppress_secret_digests: bool = False,
    ) -> None:
        matches = result.get("match_count", 0)
        if ignore_auth_paths and matches:
            surfaces = result.get("matched_surfaces", [])
            matches = sum(
                1
                for surface in surfaces
                if not str(surface).endswith("/auth.json")
            )
        # An incomplete scan is itself a failure even when no match was
        # observed.  Formal evidence intentionally exposes only bounded counts;
        # paths, raw values and provider-key digests stay internal.
        scan_complete = bool(result.get("scan_complete", True))
        scan_error_count = result.get("scan_error_count", 0)
        try:
            scan_error_count = max(0, int(scan_error_count))
        except (TypeError, ValueError):
            scan_error_count = 1
            scan_complete = False
        if not suppress_secret_digests and not matches and not scan_complete:
            # Preserve the legacy non-formal evidence shape; formal aggregate
            # cleanup uses the explicit fail-closed scan fields below.
            return
        if matches or not scan_complete:
            if suppress_secret_digests:
                self._secret_audit_failures[identity] = {
                    "scanned_files": max(0, int(result.get("scanned_files", 0) or 0)),
                    "match_count": max(0, int(matches or 0)),
                    "matched_secret_count": max(
                        0, int(result.get("matched_secret_count", 0) or 0)
                    ),
                    "scan_complete": scan_complete,
                    "scan_error_count": scan_error_count,
                }
            else:
                self._secret_audit_failures[identity] = {
                    "scanned_files": result.get("scanned_files", 0),
                    "match_count": matches,
                    "matched_secret_count": result.get("matched_secret_count", 0),
                    "matched_secret_digests": list(result.get("matched_secret_digests", [])),
                }

    @staticmethod
    def _safe_cleanup_audit(result: Mapping[str, Any]) -> dict[str, int | bool]:
        """Project one audit to safe counts/booleans only."""

        try:
            scanned_files = max(0, int(result.get("scanned_files", 0) or 0))
        except (TypeError, ValueError):
            scanned_files = 0
        try:
            match_count = max(0, int(result.get("match_count", 0) or 0))
        except (TypeError, ValueError):
            match_count = 1
        try:
            matched_secret_count = max(0, int(result.get("matched_secret_count", 0) or 0))
        except (TypeError, ValueError):
            matched_secret_count = 1
        try:
            scan_error_count = max(0, int(result.get("scan_error_count", 0) or 0))
        except (TypeError, ValueError):
            scan_error_count = 1
        scan_complete = bool(result.get("scan_complete", True)) and scan_error_count == 0
        return {
            "scanned_files": scanned_files,
            "match_count": match_count,
            "matched_secret_count": matched_secret_count,
            "scan_complete": scan_complete,
            "scan_error_count": scan_error_count,
        }

    def acceptance_child_factory(self, spec: dict[str, Any]) -> Any:
        """Create one private Source/Platform Examiner child.

        An explicitly supplied factory is retained as a deterministic unit-test seam.  All
        normal formal Acceptance calls use ``_launch_acceptance_child`` and therefore create
        a private process/session/thread with a bounded first turn.
        """
        if not isinstance(spec, dict) or not isinstance(spec.get("child_handle_digest"), str):
            raise CodexRuntimeError("acceptance child descriptor is invalid")
        if spec["child_handle_digest"] in self._acceptance_children:
            raise CodexRuntimeError("acceptance child handle is already active")
        # The resource itself removes this handle during destroy/recycle.  Adapter.stop
        # remains an idempotent final sweep, but Acceptance can now prove registry zero
        # residue immediately after a direct recycle.
        spec.setdefault(
            "_registry_remove",
            lambda handle: self._acceptance_children.pop(handle, None),
        )
        if self._acceptance_child_factory is not None:
            resource = self._acceptance_child_factory(spec)
        elif all(
            isinstance(spec.get(field), str) and spec.get(field)
            for field in ("private_root", "private_input", "ticket_digest", "input_digest", "session_id")
        ):
            resource = self._launch_acceptance_child(spec)
        else:
            # A tiny legacy/preflight descriptor has no enough frozen input to launch a
            # child.  Keep it as a private cleanup record; formal Runner specs always
            # include the fields above and take the real path.
            resource = _CodexChildResource(spec)
        if not getattr(resource, "destroyed", False):
            self._acceptance_children[spec["child_handle_digest"]] = resource
        return resource

    def launch_lean_examiner_child(
        self,
        packet: ExaminerRolePacket,
        metrics: ExaminerRunMetrics,
        *,
        read_key: str | None = None,
        platform_forwarder: Callable[[str, Mapping[str, Any], str], Mapping[str, Any]] | None = None,
        timeout_seconds: float = 90.0,
    ) -> Any:
        """Launch one R2.3-006 fresh child through the existing Codex child factory.

        This is the production wiring seam used by independent local acceptance checks;
        it does not reuse a persistent role.  Platform scope/key are read only from the
        immutable packet, and the child callback receives one typed terminal payload.
        """

        if not isinstance(packet, ExaminerRolePacket) or packet.kind not in {"source", "platform", "acceptance"}:
            raise CodexRuntimeError("lean Examiner packet is invalid")
        if not isinstance(metrics, ExaminerRunMetrics):
            raise CodexRuntimeError("lean Examiner metrics object is invalid")
        if packet.kind == "platform" and (
            not isinstance(read_key, str)
            or not read_key
            or not callable(platform_forwarder)
        ):
            # A Platform Examiner is only runnable with the ticket-bound host
            # proxy.  Reject before child creation so no proxy/backend call can
            # occur on an incomplete capability envelope.
            raise ExaminerRuntimeBlocked(
                "acceptance-input",
                role="platform",
                evidence={"read_key": bool(read_key), "forwarder": callable(platform_forwarder)},
            )
        payload = _unfreeze_packet(packet.payload)
        private_root = Path(tempfile.mkdtemp(prefix="r23006-examiner-", dir="/tmp"))
        os.chmod(private_root, 0o700)
        private_input = private_root / "input.json"
        self._write_child_private(private_input, _packet_canonical(payload), 0o400)
        # The lean child has no filesystem/tools capability by design.  Inject the
        # complete immutable packet into its first turn so the source bytes and
        # binding fields are available without widening the role's MCP inventory.
        # ``_packet_canonical`` encodes bytes as explicit base64 objects; source
        # bytes remain separately accounted from host packet tokens in metrics.
        packet_json = _packet_canonical(payload).decode("utf-8")
        source_text_json = ""
        if packet.kind == "source":
            source_text = []
            for source in payload.get("approved_sources", ()):
                if not isinstance(source, Mapping) or not isinstance(source.get("bytes"), bytes):
                    raise ExaminerRuntimeBlocked("source-missing", role="source")
                try:
                    text = source["bytes"].decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise ExaminerRuntimeBlocked("source-missing", role="source") from exc
                source_text.append({"path": source.get("path"), "sha256": source.get("sha256"), "text": text})
            source_text_json = " SOURCE_TEXT_JSON=" + json.dumps(
                source_text, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
        role_instruction = ""
        if packet.kind == "platform":
            role_instruction = (
                " PLATFORM_TEXT_FALLBACK=After calling submit_examiner_report, also write "
                "one JSON object in your reply text with exactly the top-level keys "
                "answerability, conclusion, evidence, coverage, gaps, evidence_refs. "
                "evidence_refs must contain every successful proxy call in order with "
                "the exact request_digest, response_digest, artifact_path, ref_id, tool, "
                "and page the tool returned."
            )
        if packet.kind == "acceptance":
            source_ids = payload.get("source_evidence_ref_ids")
            platform_ids = payload.get("platform_evidence_ref_ids")
            if not isinstance(source_ids, (list, tuple)):
                source_ids = []
            if not isinstance(platform_ids, (list, tuple)):
                platform_ids = []
            normalized_source_ids = [str(value) for value in source_ids]
            normalized_platform_ids = [str(value) for value in platform_ids]
            pass_evidence_ids = list(dict.fromkeys(
                [*normalized_source_ids, *normalized_platform_ids]
            ))
            acceptance_ids = json.dumps(
                {
                    "source_evidence_ref_ids": normalized_source_ids,
                    "platform_evidence_ref_ids": normalized_platform_ids,
                    "pass_evidence_ref_ids": pass_evidence_ids,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            role_instruction = (
                " ACCEPTANCE_VERDICT_TASK=In your first inference call the "
                "submit_examiner_report tool exactly once with status=PASS/FAIL/BLOCKED, "
                "answer=one bounded sentence, current/usable=booleans, and "
                "failure_layer/blocked_reason=null when PASS. For a PASS verdict set "
                "evidence_ref_ids exactly to the flat list pass_evidence_ref_ids inside "
                "EVIDENCE_IDS_JSON; never add p-numbers or source: IDs you generated "
                "yourself. Do not reason again. "
                "ACCEPTANCE_TEXT_FALLBACK=After the tool call, also write one JSON object "
                "in your reply text with exactly the keys status, answer, "
                "evidence_ref_ids, current, usable, failure_layer, blocked_reason. "
                "EVIDENCE_IDS_JSON=" + acceptance_ids
            )
        first_turn_text = (
            "R2.3-006 fresh immutable packet. Use only this serialized packet and submit "
            "one typed terminal report through the report-only examiner MCP server. "
            "Do not use any other context or contact other roles. PACKET_JSON="
            + packet_json
            + source_text_json
            + role_instruction
            + f" PACKET_DIGEST={packet.canonical_digest}"
        )
        handle_digest = hashlib.sha256((packet.canonical_digest + metrics.role).encode()).hexdigest()
        binding = payload.get("ticket_binding") if isinstance(payload.get("ticket_binding"), Mapping) else {}
        ticket_digest = str(binding.get("ticket_digest", "0" * 64)) if packet.kind in {"platform", "acceptance"} else str(payload.get("ticket_digest", "0" * 64))
        model_state = payload.get("model_state", {}) if isinstance(payload.get("model_state"), Mapping) else {}
        scope = payload.get("platform_read_scope", {}) if isinstance(payload.get("platform_read_scope"), Mapping) else {}
        reports: list[Mapping[str, Any]] = []
        report_kind = packet.kind
        spec: dict[str, Any] = {
            # Reuse the reviewed formal model/provider binding.  The task id is
            # deliberately independent from the persistent Runner workflow; only
            # model selection is inherited here.
            "task_id": FORMAL_MODEL_TASK_ID,
            "acceptance_round_id": str(payload.get("acceptance_round_id", "r23006-round")),
            "kind": report_kind,
            "attempt": 0,
            "session_id": f"lean-{handle_digest[:16]}",
            "child_handle_digest": handle_digest,
            "ticket_digest": ticket_digest if re.fullmatch(r"[0-9a-f]{64}", ticket_digest) else "0" * 64,
            "input_digest": packet.canonical_digest,
            "private_root": str(private_root),
            "private_input": str(private_input),
            "platform_read_scope": dict(scope),
            "model_state_digest": str(model_state.get("state_digest", "0" * 64)),
            "allowed_read_tools": list(payload.get("allowed_read_tools", ())) if packet.kind == "platform" else [],
            "timeout_seconds": timeout_seconds,
            "read_key_plaintext": read_key,
            "formal_platform": packet.kind == "platform",
            "platform_forwarder": platform_forwarder,
            "lean_examiner": True,
            "report_submit_payload": reports.append,
            "_metrics": metrics,
            "_packet": packet,
            "_submitted_reports": reports,
            "first_turn_input": [
                {
                    "type": "text",
                    "text": first_turn_text,
                }
            ],
        }
        if packet.kind == "platform" and read_key is None:
            shutil.rmtree(private_root, ignore_errors=True)
            raise ExaminerRuntimeBlocked("acceptance-input", role="platform")
        try:
            resource = self.acceptance_child_factory(spec)
        except Exception:
            shutil.rmtree(private_root, ignore_errors=True)
            raise
        return resource

    def bind_acceptance_model_profile(self, profile: TeamModelProfile) -> None:
        """Bind the validated team model profile for a standalone acceptance run.

        A TeamRunner run freezes its profile in ``start_roster``; the R3.0-011
        ``cq-acceptance`` carrier starts no roster, so it binds the validated
        profile itself before launching a formal child.  Coordination stays off:
        this only satisfies the formal role-binding guard that every fresh
        Examiner child already enforces.
        """

        if not isinstance(profile, TeamModelProfile):
            raise CodexRuntimeError("acceptance runtime model profile is invalid")
        self._team_model_profile = profile

    def launch_v3_acceptance_child(
        self,
        packet: AcceptanceBatchPacket,
        *,
        role_instructions: str,
        reports: list[Mapping[str, Any]],
        read_key: str | None = None,
        platform_forwarder: Callable[[str, Mapping[str, Any], str], Mapping[str, Any]] | None = None,
        timeout_seconds: float = 300.0,
        graph_set_ids: Mapping[str, Any] | None = None,
    ) -> Any:
        """Launch the single v3 hidden-batch acceptance child (R3.0-011).

        Explicit v3 dispatch: only an :class:`AcceptanceBatchPacket` whose schema
        resolves to the v3 branch is accepted here; a legacy
        ``ExaminerRolePacket/v1`` must go through ``launch_lean_examiner_child``.
        The existing child factory is reused, one session per batch, with the
        ordered batch packet bound into the first turn.
        """

        if not isinstance(packet, AcceptanceBatchPacket):
            raise CodexRuntimeError("v3 acceptance child requires a v3 batch packet")
        if acceptance_branch_for(packet.schema_version) != CQ_ACCEPTANCE_BRANCH_V3:
            raise CodexRuntimeError("v3 acceptance child requires the v3 branch")
        if not isinstance(role_instructions, str) or not role_instructions:
            raise CodexRuntimeError("v3 acceptance role instructions are invalid")
        if not isinstance(reports, list):
            raise CodexRuntimeError("v3 acceptance report sink is invalid")
        payload = _unfreeze_packet(packet.payload)
        platform_role = packet.role == CQ_ACCEPTANCE_PLATFORM_ROLE
        if platform_role and (
            not isinstance(read_key, str)
            or not read_key
            or not callable(platform_forwarder)
        ):
            raise ExaminerRuntimeBlocked(
                "acceptance-input",
                role="platform",
                evidence={"read_key": bool(read_key), "forwarder": callable(platform_forwarder)},
            )
        scope = payload.get("authorized_scope") if isinstance(payload.get("authorized_scope"), list) else []
        # The Host observes one default graph set per authorized Ontology with the
        # same read-only tools before the child exists; the child scope is built
        # from the packet binding plus these locators and nothing else.  Every
        # required Host input is validated before the private tree is allocated
        # so a rejected launch never leaves an allocated root behind.
        v3_graph_set_ids: dict[str, Any] = {}
        if platform_role:
            if not isinstance(graph_set_ids, Mapping) or not graph_set_ids:
                raise ExaminerRuntimeBlocked(
                    "acceptance-input",
                    role="platform",
                    evidence={"graph_set_ids": bool(graph_set_ids)},
                )
            v3_graph_set_ids = {
                str(key): value
                for key, value in graph_set_ids.items()
                if isinstance(key, str) and key in set(scope)
            }
            if sorted(v3_graph_set_ids) != sorted(str(item) for item in scope) or any(
                not isinstance(value, str) or not value for value in v3_graph_set_ids.values()
            ):
                raise ExaminerRuntimeBlocked(
                    "acceptance-input",
                    role="platform",
                    evidence={"graph_set_ids": "incomplete"},
                )
        private_root = Path(tempfile.mkdtemp(prefix="r3011-acceptance-", dir="/tmp"))
        os.chmod(private_root, 0o700)
        private_input = private_root / "input.json"
        self._write_child_private(private_input, _packet_canonical(payload), 0o400)
        if platform_role:
            # The Platform Examiner stays blind: no answer, no evidence bundle.
            isolation = (
                "One continuous session per batch, questions in packet order, no "
                "answer text, no source directory, no evidence bundle, no other context."
            )
        else:
            isolation = (
                "One independent judging session per batch, questions in packet order; "
                "this packet already carries the frozen answer points, the approved "
                "evidence material and the Examiner reports, and no platform read is "
                "available to you."
            )
        first_turn_text = (
            "R3.0-011 v3 hidden-batch acceptance session. Use only this serialized packet "
            "and submit per-question v3 reports through the report-only acceptance MCP "
            "server. "
            + isolation
            + " PACKET_JSON="
            + _packet_canonical(payload).decode("utf-8")
            + " "
            + role_instructions
            + f" PACKET_DIGEST={packet.canonical_digest}"
        )
        binding = payload.get("model_binding") if isinstance(payload.get("model_binding"), Mapping) else {}
        ontologies = binding.get("ontologies") if isinstance(binding.get("ontologies"), list) else []
        state_digest = "0" * 64
        if ontologies and isinstance(ontologies[0], Mapping):
            workspace = ontologies[0].get("workspace_state")
            if isinstance(workspace, Mapping) and isinstance(workspace.get("state_digest"), str):
                state_digest = workspace["state_digest"]
        handle_digest = hashlib.sha256(
            (packet.canonical_digest + packet.role).encode()
        ).hexdigest()
        spec: dict[str, Any] = {
            "task_id": FORMAL_MODEL_TASK_ID,
            "acceptance_round_id": f"r3011-{packet.batch_id}",
            "kind": "platform" if platform_role else "acceptance",
            "attempt": 0,
            "session_id": f"r3011-{handle_digest[:16]}",
            "child_handle_digest": handle_digest,
            "ticket_digest": packet.freeze_digest,
            "input_digest": packet.canonical_digest,
            "private_root": str(private_root),
            "private_input": str(private_input),
            "platform_read_scope": {"ontology_ids": list(scope)},
            "v3_graph_set_ids": v3_graph_set_ids,
            "model_state_digest": state_digest,
            "allowed_read_tools": (
                list(payload.get("authorized_read_tools", ())) if platform_role else []
            ),
            "timeout_seconds": timeout_seconds,
            "read_key_plaintext": read_key,
            "formal_platform": platform_role,
            "platform_forwarder": platform_forwarder,
            "v3_batch": True,
            "v3_role": packet.role,
            "v3_packet": packet,
            "lean_examiner": True,
            "report_submit_payload": reports.append,
            "_packet": packet,
            "_submitted_reports": reports,
            "first_turn_input": [{"type": "text", "text": first_turn_text}],
        }
        try:
            resource = self.acceptance_child_factory(spec)
        except Exception:
            shutil.rmtree(private_root, ignore_errors=True)
            raise
        return resource

    def run_v3_acceptance_child(
        self,
        packet: AcceptanceBatchPacket,
        *,
        role_instructions: str,
        reports: list[Mapping[str, Any]],
        read_key: str | None = None,
        platform_forwarder: Callable[[str, Mapping[str, Any], str], Mapping[str, Any]] | None = None,
        timeout_seconds: float = 300.0,
        graph_set_ids: Mapping[str, Any] | None = None,
        teardown: dict[str, Any] | None = None,
    ) -> list[Mapping[str, Any]]:
        """Run one v3 batch child to batch completion and return its reports.

        Launch, wait and report ingestion in one call: the ordered per-question
        reports are ingested from the same list the private sink appended to, so
        the Host consumes exactly what passed the batch contract at submit time.
        Completion is the sink's own batch-complete latch, never a timeout race
        or a model statement; anything else (infrastructure failure, dead child,
        deadline) raises :class:`ExaminerRuntimeBlocked` and the child is
        destroyed, so a missing or partial batch can never look like a PASS.

        Two v3-only observables are handed back to the carrier without touching
        the shared legacy teardown: ``teardown`` (when given) receives the
        child's actual post-``destroy`` teardown outcome, and the caller's
        ``reports`` list keeps every report the sink already accepted -- legacy
        cleanup clears that shared list, and a failed batch must still be able
        to name the questions that did land.
        """

        resource = self.launch_v3_acceptance_child(
            packet,
            role_instructions=role_instructions,
            reports=reports,
            read_key=read_key,
            platform_forwarder=platform_forwarder,
            timeout_seconds=timeout_seconds,
            graph_set_ids=graph_set_ids,
        )
        expected = 0
        # Observed before destroy(): the legacy teardown pops the socket root
        # from the spec and stops the servers, so this is the last point where
        # the v3 boundary can capture what it owns.
        proxy = getattr(resource, "proxy", None)
        report_sink = getattr(resource, "report_sink", None)
        private_root = str(resource.spec.get("private_root") or "")
        socket_root = str(resource.spec.get("_runtime_socket_root") or "")
        try:
            sink = getattr(resource, "report_sink", None)
            contract = getattr(sink, "batch_contract", None)
            if not isinstance(contract, V3BatchReportContract):
                raise ExaminerRuntimeBlocked(
                    "runtime-infrastructure",
                    role=packet.role,
                    evidence={"reason_code": "batch-contract-unavailable"},
                )
            expected = len(contract.question_ids)
            deadline = time.monotonic() + max(0.1, float(timeout_seconds))
            while time.monotonic() < deadline:
                blocked = getattr(resource, "blocked", None)
                if isinstance(blocked, ExaminerRuntimeBlocked):
                    raise blocked
                failure = getattr(resource, "failure_evidence", None)
                failure = failure() if callable(failure) else None
                if isinstance(failure, Mapping):
                    raise ExaminerRuntimeBlocked(
                        "runtime-infrastructure", role=packet.role, evidence=dict(failure)
                    )
                received = getattr(resource, "submitted_reports", None)
                count = len(received) if isinstance(received, (list, tuple)) else 0
                if count >= expected:
                    process = getattr(resource, "process", None)
                    poll = getattr(process, "poll", None)
                    if callable(poll) and poll() is None:
                        # Reports are in; let the App Server turn settle so the
                        # child is destroyed from a quiet state, not mid-write.
                        time.sleep(0.2)
                    return list(received)
                process = getattr(resource, "process", None)
                poll = getattr(process, "poll", None)
                if callable(poll) and poll() is not None:
                    raise ExaminerRuntimeBlocked(
                        "runtime-infrastructure",
                        role=packet.role,
                        evidence={"reason_code": "child-exited", "reports": count},
                    )
                time.sleep(0.05)
            raise ExaminerRuntimeBlocked(
                "runtime-infrastructure",
                role=packet.role,
                evidence={"reason_code": "batch-incomplete", "reports": len(reports)},
            )
        finally:
            # Snapshot before destroy(): the shared list is this caller's own
            # list and legacy cleanup clears it, so the accepted values must be
            # put back afterwards or a partial batch is silently discarded.
            accepted = list(reports)
            destroy_error: str | None = None
            # ``ReportSinkServer.stop()`` clears ``_thread``, so the serve
            # thread handle must be captured before destroy for liveness to be
            # a meaningful "is it still running" signal.
            sink_thread = getattr(report_sink, "_thread", None)
            try:
                destroy = getattr(resource, "destroy", None)
                if callable(destroy):
                    destroy()
            except Exception as exc:
                # Legacy ``destroy`` stays unmodified; its failure is teardown
                # evidence, never a reason to skip restoring the caller's
                # accepted reports.
                destroy_error = f"{type(exc).__name__}: {exc}"
            finally:
                # Inner finally: the restoration cannot be skipped by a
                # destroy error above.
                reports[:] = accepted
            if isinstance(teardown, dict):
                teardown.clear()
                teardown.update(
                    _v3_child_teardown_evidence(
                        resource,
                        proxy=proxy,
                        report_sink=report_sink,
                        private_root=private_root,
                        socket_root=socket_root,
                        sink_thread=sink_thread,
                    )
                )
                if destroy_error is not None:
                    teardown["destroy_error"] = destroy_error

    def run_lean_examiner_child(
        self,
        packet: ExaminerRolePacket,
        metrics: ExaminerRunMetrics,
        *,
        read_key: str | None = None,
        platform_forwarder: Callable[[str, Mapping[str, Any], str], Mapping[str, Any]] | None = None,
        timeout_seconds: float = 90.0,
    ) -> Mapping[str, Any]:
        """Execute one fresh Examiner child and return its validated terminal payload.

        The caller owns the metrics object; the real App Server thread identity and
        notification accounting are bound during launch.  This method waits for the
        private report sink, then destroys the child before returning so no resource
        or temporary key survives a Source/Platform/Acceptance turn.
        """

        resource = self.launch_lean_examiner_child(
            packet,
            metrics,
            read_key=read_key,
            platform_forwarder=platform_forwarder,
            timeout_seconds=timeout_seconds,
        )
        report: Mapping[str, Any] | None = None
        try:
            deadline = time.monotonic() + max(0.1, float(timeout_seconds))
            while time.monotonic() < deadline:
                blocked = getattr(resource, "blocked", None)
                if isinstance(blocked, ExaminerRuntimeBlocked):
                    raise blocked
                evidence = getattr(resource, "failure_evidence", None)
                failure = evidence() if callable(evidence) else None
                if isinstance(failure, Mapping):
                    try:
                        submitted_reports = getattr(resource, "submitted_reports", ())
                        report_received = isinstance(submitted_reports, (list, tuple)) and bool(submitted_reports)
                    except Exception:
                        report_received = False
                    try:
                        terminal_value = getattr(resource, "terminal_event", False)
                        terminal_event = terminal_value if isinstance(terminal_value, bool) else False
                    except Exception:
                        terminal_event = False
                    try:
                        proxy = getattr(resource, "proxy", None)
                        receipt_snapshot = getattr(proxy, "receipt_snapshot", ()) if proxy is not None else ()
                        if callable(receipt_snapshot):
                            receipt_snapshot = receipt_snapshot()
                        proxy_receipt_count = (
                            len(receipt_snapshot)
                            if isinstance(receipt_snapshot, (list, tuple))
                            else 0
                        )
                    except Exception:
                        proxy_receipt_count = 0
                    safe_failure = {
                        key: value
                        for key, value in failure.items()
                        if key in {"failure_category", "reason_code"}
                    }
                    safe_failure.update(
                        report_received=report_received,
                        terminal_event=terminal_event,
                        proxy_receipt_count=proxy_receipt_count,
                    )
                    continuation = getattr(resource, "_continuation_reason", None)
                    if isinstance(continuation, str) and continuation in {"sent", "rpc-failed"}:
                        safe_failure["continuation"] = continuation
                    raise ExaminerRuntimeBlocked(
                        "runtime-infrastructure",
                        role=packet.kind,
                        evidence=safe_failure,
                    )
                reports = getattr(resource, "submitted_reports", None)
                if report is None and isinstance(reports, list) and reports:
                    candidate = reports[0]
                    if not isinstance(candidate, Mapping):
                        raise ExaminerRuntimeBlocked(
                            "acceptance-evidence",
                            role=packet.kind,
                            evidence={"binding_code": "submitted-report-shape"},
                        )
                    report = dict(candidate)
                    if packet.kind == "source":
                        _source_report_evidence_ids(packet, report)
                    elif packet.kind == "platform":
                        _validate_platform_report_receipts(report, resource)
                    if packet.kind == "acceptance":
                        allowed_ids = set()
                        for field in ("source_evidence_ref_ids", "platform_evidence_ref_ids"):
                            values = packet.payload.get(field)
                            if isinstance(values, (list, tuple)):
                                allowed_ids.update(str(value) for value in values)
                        _validate_acceptance_evidence_ids(report, allowed_ids)
                        metrics.record_terminal_verdict(report)
                    else:
                        metrics.record_terminal_report(report)
                # A report callback is not the provider terminal event.  Real
                # resources expose this latch from the private stdout observer;
                # keep checking it after the one-time report validation.  The
                # validated typed report is itself the terminal payload, so a
                # missing provider terminal event must not turn a successful
                # submission into a timeout.  A short accounting grace lets late
                # thread/tokenUsage notifications land after a fast Source tool
                # call; the Host never waits indefinitely for turn/completed.
                if report is not None:
                    accounting_deadline = time.monotonic() + 3.0
                    while time.monotonic() < accounting_deadline:
                        blocked = getattr(resource, "blocked", None)
                        if isinstance(blocked, ExaminerRuntimeBlocked):
                            raise blocked
                        if (
                            getattr(metrics, "inference_steps", 0) > 0
                            or getattr(resource, "terminal_event", False)
                        ):
                            break
                        time.sleep(0.02)
                    return report
                # Acceptance models often end their turn with the verdict written
                # in reply text instead of calling the submit tool.  When the
                # turn is over (or the model has already reasoned several steps
                # without submitting) and no typed report arrived, extract a
                # strict verdict object from the agent's message deltas.
                if (
                    report is None
                    and packet.kind == "acceptance"
                    and (
                        getattr(resource, "terminal_event", False)
                        or getattr(metrics, "inference_steps", 0) >= 3
                    )
                ):
                    resource._text_verdict_tried = True
                    agent = getattr(resource, "_child_agent", None)
                    text_verdict = self._extract_verdict_from_text(agent)
                    if text_verdict is not None:
                        resource.submitted_reports.append(text_verdict)
                        continue
                if (
                    report is None
                    and packet.kind == "platform"
                    and (
                        getattr(resource, "terminal_event", False)
                        or getattr(metrics, "inference_steps", 0) >= 3
                    )
                ):
                    platform_agent = getattr(resource, "_child_agent", None)
                    text_report = self._extract_platform_report_from_text(platform_agent)
                    if text_report is not None:
                        resource.submitted_reports.append(text_report)
                        continue
                # The model sometimes ends its turn after the retrieval wave
                # without submitting the report (a DeepSeek reasoning behavior),
                # or goes idle without a terminal event.  One mechanical
                # continuation is allowed so the child can complete the
                # submission; it is never a second retrieval wave or a
                # collaboration channel.  Trigger it when the wave has produced
                # at least one inference and the deadline is approaching but the
                # report is still missing.  Platform (wave-then-stop) and
                # Acceptance (reasoning-without-submit) both need the nudge;
                # Source submits directly and would exceed the 3-step budget.
                platform_receipt_count = 0
                if packet.kind == "platform":
                    try:
                        proxy = getattr(resource, "proxy", None)
                        snapshots = getattr(proxy, "receipt_snapshot", ()) if proxy is not None else ()
                        if callable(snapshots):
                            snapshots = snapshots()
                        platform_receipt_count = (
                            len(snapshots) if isinstance(snapshots, (list, tuple)) else 0
                        )
                    except Exception:
                        platform_receipt_count = 0
                platform_saturated = bool(
                    packet.kind == "platform"
                    and (
                        getattr(metrics, "inference_steps", 0) >= 3
                        or platform_receipt_count >= 8
                    )
                )
                if (
                    packet.kind in {"platform", "acceptance"}
                    and report is None
                    and getattr(resource, "_continuation_count", 0) < 3
                    and (
                        getattr(resource, "terminal_event", False)
                        or platform_saturated
                        or (
                            getattr(metrics, "inference_steps", 0) >= 1
                            and time.monotonic() >= deadline - max(10.0, float(timeout_seconds) * 0.35)
                        )
                        or (
                            packet.kind == "acceptance"
                            and getattr(metrics, "inference_steps", 0) >= 1
                        )
                    )
                    and (
                        getattr(resource, "_continuation_count", 0) == 0
                        or (
                            getattr(resource, "_continuation_count", 0) == 1
                            and time.monotonic() - getattr(resource, "_continuation_at", 0.0) >= 10.0
                        )
                        or (
                            getattr(resource, "_continuation_count", 0) == 2
                            and time.monotonic() - getattr(resource, "_continuation_at", 0.0) >= 15.0
                        )
                    )
                ):
                    agent = getattr(resource, "_child_agent", None)
                    if agent is not None and getattr(agent, "thread_id", None):
                        resource._continuation_count = getattr(resource, "_continuation_count", 0) + 1
                        resource._continuation_at = time.monotonic()
                        allow = getattr(metrics, "allow_continuation_turn", None)
                        if callable(allow):
                            try:
                                allow()
                            except Exception:
                                pass
                        try:
                            if packet.kind == "acceptance":
                                input_text = (
                                    "STOP analyzing. You must NOW call the "
                                    "submit_examiner_report tool exactly once. Use "
                                    "status = PASS/FAIL/BLOCKED, answer = one bounded "
                                    "sentence, evidence_ref_ids = the Host-provided IDs "
                                    "you cited, current/usable = booleans, and "
                                    "failure_layer/blocked_reason = null when PASS. "
                                    "Do not reason further, do not re-read the packet. "
                                    "The tool call itself is the only valid final action."
                                )
                            else:
                                if packet.kind == "platform" and platform_receipt_count:
                                    input_text = (
                                        f"STOP querying. You already have "
                                        f"{platform_receipt_count} successful read calls; "
                                        "do not make another read. Build the terminal report "
                                        "from what you already received and call "
                                        "submit_examiner_report exactly once now. "
                                        "evidence_refs must contain every successful call "
                                        "in order as p0..p"
                                        f"{platform_receipt_count - 1} with the exact "
                                        "request_digest/response_digest/artifact_path the tool "
                                        "returned. Do not reason further, do not re-read, do "
                                        "not plan. The tool call itself is the only valid "
                                        "final action."
                                    )
                                else:
                                    input_text = (
                                        "STOP analyzing. You must NOW call the "
                                        "submit_examiner_report tool exactly once with "
                                        "your typed terminal report built from what you "
                                        "already have. Do not reason further, do not "
                                        "re-read anything, do not plan. The tool call "
                                        "itself is the only valid final action."
                                    )
                            active_turn_id = getattr(agent, "active_turn_id", None)
                            if isinstance(active_turn_id, str) and active_turn_id:
                                try:
                                    self._rpc(
                                        agent,
                                        "turn/steer",
                                        {
                                            "threadId": agent.thread_id,
                                            "expectedTurnId": active_turn_id,
                                            "input": [{"type": "text", "text": input_text}],
                                        },
                                    )
                                except Exception:
                                    self._rpc(
                                        agent,
                                        "turn/start",
                                        {
                                            "threadId": agent.thread_id,
                                            "input": [{"type": "text", "text": input_text}],
                                        },
                                    )
                            else:
                                self._rpc(
                                    agent,
                                    "turn/start",
                                    {
                                        "threadId": agent.thread_id,
                                        "input": [{"type": "text", "text": input_text}],
                                    },
                                )
                            resource._continuation_reason = "sent"
                        except Exception:
                            resource._continuation_reason = "rpc-failed"
                process = getattr(resource, "process", None)
                poll = getattr(process, "poll", None)
                if callable(poll) and poll() is not None and not getattr(resource, "destroyed", False):
                    raise ExaminerRuntimeBlocked("runtime-infrastructure", role=packet.kind)
                time.sleep(0.01)
            timeout_evidence: dict[str, Any] = {}
            continuation = getattr(resource, "_continuation_reason", None)
            if isinstance(continuation, str) and continuation in {"sent", "rpc-failed"}:
                timeout_evidence["continuation"] = continuation
            raise ExaminerRuntimeBlocked(
                "runtime-infrastructure", role=packet.kind, evidence=timeout_evidence
            )
        finally:
            destroy = getattr(resource, "destroy", None)
            if callable(destroy):
                destroy()

    @staticmethod
    def _child_package_assets(
        kind: str, root: Path, *, v3_batch: bool = False
    ) -> tuple[Path, Path, Path]:
        if kind not in {"source", "platform", "acceptance"}:
            raise CodexRuntimeError("Examiner child kind is invalid")
        if v3_batch:
            # R3.0-011: the ordered v3 batch mounts its own prompt assets.  The
            # legacy package/skill bytes mandate one single-question payload,
            # the old evidence shape, a Source Examiner and a 3-inference cap,
            # which contradicts the packet contract the sink enforces -- and a
            # first-turn note cannot reliably override mounted role
            # instructions.  The legacy bytes stay byte-identical and remain
            # the only assets for every non-v3 child.
            if kind not in {"platform", "acceptance"}:
                raise CodexRuntimeError("v3 acceptance child kind is invalid")
            package = root / "modeling_team" / "agent-packages" / "v3-acceptance-batch"
            instructions = package / (
                "platform-examiner.md" if kind == "platform" else "acceptance-judge.md"
            )
            skill = package / "SKILL.md"
            for path in (instructions, skill):
                try:
                    metadata = os.lstat(path)
                except OSError as exc:
                    raise CodexRuntimeError("v3 Examiner package asset is unavailable") from exc
                if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                    raise CodexRuntimeError("v3 Examiner package asset is invalid")
            return package / "package.yaml", instructions, skill
        package = root / "modeling_team" / "agent-packages" / (
            f"{kind}-examiner" if kind != "acceptance" else "acceptance-examiner"
        )
        instructions = package / "instructions.md"
        skill = (
            root
            / "skills"
            / (
                "source-examiner"
                if kind == "source"
                else "platform-examiner"
                if kind == "platform"
                else "lean-acceptance-examiner"
            )
            / "SKILL.md"
        )
        for path in (instructions, skill):
            try:
                metadata = os.lstat(path)
            except OSError as exc:
                raise CodexRuntimeError("Examiner package asset is unavailable") from exc
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                raise CodexRuntimeError("Examiner package asset is invalid")
        return package / "package.yaml", instructions, skill

    def _codex_companion_binary(self) -> Path | None:
        """Resolve Codex 0.147.0's tool-execution companion next to the binary.

        Codex spawns ``codex-code-mode-host`` for every tool/shell execution and
        resolves it relative to its own executable directory, so inside a
        Runtime namespace that mounts only ``codex`` every tool call dies with
        ``failed to spawn code-mode host ... No such file or directory`` (R2.3-008
        start6).  The companion ships in the same release ``bin`` directory.
        Returns ``None`` when the installed Codex has no companion (older or
        newer layouts), keeping the namespace additive and startup unchanged.
        """

        binary = shutil.which(self.codex_binary) or self.codex_binary
        companion = Path(binary).resolve().parent / "codex-code-mode-host"
        try:
            metadata = os.lstat(companion)
        except OSError:
            return None
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            return None
        if not os.access(companion, os.X_OK):
            return None
        return companion

    def _acceptance_namespace_command(
        self,
        *,
        home: Path,
        work: Path,
        skills: Path,
        proxy_socket: Path | None,
        report_socket: Path,
    ) -> list[str]:
        binary = shutil.which(self.codex_binary) or self.codex_binary
        if not self.use_bwrap:
            return [binary, "app-server"]
        bwrap = shutil.which("bwrap")
        if not bwrap:
            raise CodexRuntimeError("bubblewrap is required for private Examiner isolation")
        command = [
            bwrap,
            "--die-with-parent",
            "--unshare-pid",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
        ]
        for source in (
            "/usr",
            "/bin",
            "/lib",
            "/lib64",
            "/etc/ld.so.cache",
            "/etc/resolv.conf",
            "/etc/hosts",
            "/etc/nsswitch.conf",
            "/etc/ssl/certs",
        ):
            if Path(source).exists():
                command.extend(["--ro-bind", source, source])
        command += [
            "--dir",
            "/agent",
            "--bind",
            str(home),
            "/agent/home",
            "--bind",
            str(work),
            "/agent/work",
            "--ro-bind",
            str(skills),
            "/skills",
            "--bind",
            str(report_socket),
            "/agent/home/report.sock",
        ]
        if proxy_socket is not None:
            command.extend(["--bind", str(proxy_socket), "/agent/home/platform-proxy.sock"])
        command += [
            "--chdir",
            "/agent/work",
            "--setenv",
            "CODEX_HOME",
            "/agent/home",
            "--setenv",
            "HOME",
            "/agent/home",
            "--setenv",
            "PATH",
            "/usr/local/bin:/usr/bin:/bin",
            "--setenv",
            "TERM",
            "xterm-256color",
            "--setenv",
            "LANG",
            "C.UTF-8",
            "--setenv",
            "LC_ALL",
            "C.UTF-8",
            "--dir",
            "/agent/bin",
            "--ro-bind",
            binary,
            "/agent/bin/codex",
        ]
        # R2.3-008 start6: Examiner children execute tools too, so the Codex
        # 0.147.0 companion must sit beside the mounted binary (argv[0]-relative
        # resolution).  Absent companion degrades exactly like the old surface.
        companion = self._codex_companion_binary()
        if companion is not None:
            command += ["--ro-bind", str(companion), "/agent/bin/codex-code-mode-host"]
        command += [
            "--",
            "/agent/bin/codex",
            "--config",
            'web_search="disabled"',
            "--disable",
            "apps",
            "--disable",
            "plugins",
            "--disable",
            "multi_agent",
            "--disable",
            "multi_agent_v2",
            "--disable",
            "browser_use",
            "--disable",
            "computer_use",
            "--disable",
            "image_generation",
            "--disable",
            "memories",
            "--disable",
            "hooks",
            "app-server",
        ]
        return command

    def _launch_acceptance_child(self, spec: dict[str, Any]) -> _CodexChildResource:
        """Launch one child, converting startup failures into typed retry readiness."""
        try:
            return self._launch_acceptance_child_impl(spec)
        except Exception:
            # Keep startup failures in the same bounded attempt contract as watchdog
            # crash/timeout.  ``start_child`` has already published the provisional
            # opaque handle, so the callback can durably bind the failure before this
            # placeholder resource is returned for Acceptance get-report/recycle.
            callback = spec.get("record_infrastructure_failure")
            failure = None
            if callable(callback):
                try:
                    failure = callback("runtime", "child-start-failed")
                except Exception:
                    failure = None
            for name in ("_runtime_proxy", "_runtime_report_sink"):
                runtime = spec.pop(name, None)
                stopper = getattr(runtime, "destroy", None) or getattr(runtime, "stop", None)
                if callable(stopper):
                    try:
                        stopper()
                    except Exception:
                        pass
            revoke = spec.get("read_key_revoke")
            key_id = spec.get("read_key_id")
            if callable(revoke) and isinstance(key_id, str):
                try:
                    revoke(key_id)
                except Exception:
                    pass
            private_root = spec.get("private_root")
            if self._coordination_enabled and isinstance(private_root, str) and private_root:
                path = Path(private_root)
                if not path.is_symlink():
                    shutil.rmtree(path, ignore_errors=True)
            socket_root = spec.pop("_runtime_socket_root", None)
            if isinstance(socket_root, str) and socket_root:
                path = Path(socket_root)
                if not path.is_symlink():
                    shutil.rmtree(path, ignore_errors=True)
            spec.pop("read_key_plaintext", None)
            spec.pop("platform_forwarder", None)
            resource = _CodexChildResource(spec)
            resource.failure_category = "runtime"
            resource.failure_reason = "child-start-failed"
            resource.infrastructure_failure = failure
            resource._failure_recorded = True
            # All process/proxy/socket state has already been torn down.  Acceptance
            # retains only this typed failure placeholder for get-report/recycle; the
            # adapter registry must not retain a dead child handle.
            resource.destroyed = True
            return resource

    def _launch_acceptance_child_impl(self, spec: dict[str, Any]) -> _CodexChildResource:
        """Stage and launch a real private child; no platform call is made here."""
        kind = spec.get("kind")
        if kind not in {"source", "platform", "acceptance"}:
            raise CodexRuntimeError("Examiner child kind is invalid")
        formal = bool(
            self._coordination_enabled
            or spec.get("task_id") in {
                "r2-3-005-formal-acceptance",
                "r2-3-003-existing-scope-incremental",
            }
        )
        child_package_id = f"{kind}-examiner" if kind != "acceptance" else "acceptance"
        # R2.3-009 start21 (2026-08-22): a formal Source Examiner without the
        # carrier-staged approved bytes can only produce a manifest-citing
        # report the sink must reject; fail the child start loudly instead of
        # burning the round to the watchdog timeout.
        if formal and kind == "source":
            staged_sources_check = Path(str(spec["private_root"])) / "sources"
            if (
                not staged_sources_check.is_dir()
                or staged_sources_check.is_symlink()
                or not any(staged_sources_check.rglob("*"))
            ):
                raise CodexRuntimeError("Source Examiner approved material is unavailable")
        if formal:
            # Every fresh Examiner child uses its own package-ID binding from the
            # frozen profile: its provider session base URL, model, and effective
            # effort.  R2.3-006 lean behavior no longer overrides effort here;
            # the profile owns per-role effort selection.
            child_model_override = self._validated_formal_role_binding(child_package_id)
        else:
            child_model_override = None
        # DeepSeek is intentionally retained only for non-formal legacy adapters.
        # A formal run never resolves or injects the legacy provider key, even if
        # the Host environment still carries the historical sentinel.
        deepseek_enabled = bool(
            not formal
            and (
                spec.get("deepseek_provider") is True
                or getattr(self, "_deepseek_enabled", False)
            )
        )
        deepseek_key = self._resolve_deepseek_api_key() if deepseek_enabled else None
        private_root = Path(str(spec["private_root"]))
        try:
            root_metadata = os.lstat(private_root)
        except OSError as exc:
            raise CodexRuntimeError("Examiner private root is unavailable") from exc
        if (
            stat.S_ISLNK(root_metadata.st_mode)
            or not stat.S_ISDIR(root_metadata.st_mode)
            or stat.S_IMODE(root_metadata.st_mode) != 0o700
            or root_metadata.st_uid != os.getuid()
        ):
            raise CodexRuntimeError("Examiner private root is not 0700")
        # R3.0-011 v3: an AcceptanceBatchPacket binds the ordered hidden batch at
        # the sink itself, so a foreign batch, an unknown/duplicate/out-of-order
        # question, or a drifted content version is rejected at submit time with
        # an actionable reason.  Per-question entries still go through the
        # canonical competency_questions validators; only batch identity, order
        # and completeness are added here.  The attempt budget scales with the
        # batch so a per-question repair sequence cannot exhaust it.  Resolved
        # before the prompt assets are selected because the batch branch also
        # decides which mounted instructions and skill the session sees.
        batch_contract: V3BatchReportContract | None = None
        v3_packet = spec.get("_packet")
        if isinstance(v3_packet, AcceptanceBatchPacket):
            batch_contract = V3BatchReportContract(
                role=str(spec.get("v3_role") or v3_packet.role),
                packet=v3_packet,
            )
        _package_file, instructions, skill = self._child_package_assets(
            kind, self.root, v3_batch=batch_contract is not None
        )
        instruction_bytes = instructions.read_bytes()
        skill_bytes = skill.read_bytes()
        # Formal Examiner children on external credential routes use the shared
        # loopback provider proxy and never receive a copied host auth.json.
        # Formal ``openai-codex`` children instead receive the Host ChatGPT
        # login cache staged into their own isolated CODEX_HOME, unlinked by the
        # first-turn auth barrier before any model-selected dispatch.  Legacy/
        # non-formal child fixtures retain the historical private auth staging.
        formal_codex_builtin = bool(
            formal
            and isinstance(child_model_override, RoleModelBinding)
            and not uses_external_credential_session(child_model_override.provider_id)
        )
        paths = prepare_child_tree(
            private_root=private_root,
            host_auth=None if (formal and not formal_codex_builtin) else self.preflight_host_auth(),
            instructions=instruction_bytes,
            skill_name=skill.parent.name,
            skill_bytes=skill_bytes,
        )
        home, work, skills = paths["home"], paths["work"], paths["skills"]
        auth_payload = self._read_secret_bytes(home / "auth.json")
        self._remember_secret(auth_payload)
        # Carrier input/source bytes are staged before the adapter is invoked.  Copy only
        # the projected input into the child home; the Platform child never receives the
        # source directory, while the Source child receives exact approved bytes.
        input_path = Path(str(spec["private_input"]))
        if input_path.is_symlink() or not input_path.is_file():
            raise CodexRuntimeError("Examiner projected input is unavailable")
        self._write_child_private(home / "input.json", input_path.read_bytes(), 0o400)
        staged_sources = private_root / "sources"
        source_text_json = ""
        if kind == "source":
            if staged_sources.exists():
                if staged_sources.is_symlink() or not staged_sources.is_dir():
                    raise CodexRuntimeError("Source Examiner material tree is invalid")
                shutil.copytree(staged_sources, home / "sources", symlinks=False, dirs_exist_ok=False)
                for item in (home / "sources").rglob("*"):
                    if item.is_symlink():
                        raise CodexRuntimeError("Source Examiner material tree contains a symlink")
                    if item.is_dir():
                        os.chmod(item, 0o700)
                    if item.is_file():
                        os.chmod(item, 0o400)
                # R2.3-009 start21 (2026-08-22): the projected input.json names
                # the approved sources by path/digest only, while the package
                # instructions forbid reading staged files — so the formal
                # Source child could never quote the bytes its report must
                # cite and cited input.json locations instead.  The lean path
                # already solves this by injecting SOURCE_TEXT_JSON into the
                # first turn; replicate that seam here from the exact staged
                # bytes the carrier digest-verified against the manifest.
                source_text = []
                for path in sorted(staged_sources.rglob("*"), key=lambda p: p.relative_to(staged_sources).as_posix()):
                    if not path.is_file():
                        continue
                    data = path.read_bytes()
                    try:
                        text = data.decode("utf-8")
                    except UnicodeDecodeError as exc:
                        raise CodexRuntimeError(
                            "Source Examiner approved material is not UTF-8"
                        ) from exc
                    source_text.append({
                        "path": path.relative_to(staged_sources).as_posix(),
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "text": text,
                    })
                source_text_json = " SOURCE_TEXT_JSON=" + json.dumps(
                    source_text, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
                if formal and not source_text:
                    # The pre-launch gate above normally catches this; keep the
                    # backstop for a staged-but-empty tree.
                    raise CodexRuntimeError("Source Examiner approved material is unavailable")
        report_token = secrets.token_urlsafe(24)
        self._remember_secret(report_token.encode("utf-8"))
        report_token_path = home / "report-sink.token"
        descriptor_path = home / "examiner-descriptor.json"
        socket_root = home
        if any(len(str(home / name)) >= 100 for name in ("report.sock", "platform-proxy.sock")):
            socket_root = Path("/tmp") / f"mt-ex-{str(spec['child_handle_digest'])[:24]}"
            if socket_root.exists() or socket_root.is_symlink():
                raise CodexRuntimeError("Examiner runtime socket root already exists")
            socket_root.mkdir(mode=0o700, parents=False)
            spec["_runtime_socket_root"] = str(socket_root)
        report_socket = socket_root / "report.sock"
        # The resource owns this callback; the carrier remains the only report validator.
        submitted_reports = spec.get("_submitted_reports")
        if not isinstance(submitted_reports, list):
            submitted_reports = []
        # The private sink must receive the strict six-field child payload.  The
        # full-envelope callback remains available only to deterministic resource
        # doubles and is never installed behind a production socket.
        report_submit = spec.get("report_submit_payload")
        if not callable(report_submit):
            report_submit = spec.get("report_submit")
        report_callback = report_submit if callable(report_submit) else submitted_reports.append

        def sink_validator(report: Mapping[str, Any]) -> None:
            # Bind the child report against the live resource at submit time so a
            # rejected report returns an actionable reason and can be corrected.
            if batch_contract is not None:
                # The v3 batch contract runs inside the sink itself.
                return
            packet = spec.get("_packet")
            if not isinstance(packet, ExaminerRolePacket):
                return
            validator = _make_report_validator(kind, packet, spec.get("_runtime_resource"))
            if validator is not None:
                validator(report)

        report_sink = ReportSinkServer(
            report_socket,
            report_token,
            report_callback,
            kind=kind,
            validator=sink_validator,
            max_attempts=(
                max(3, 2 * len(batch_contract.question_ids))
                if batch_contract is not None
                else 3
            ),
            batch_contract=batch_contract,
        )
        spec["_runtime_report_sink"] = report_sink
        report_sink.start()
        def _write_private(path: Path, payload: bytes, mode: int) -> None:
            self._write_child_private(path, payload, mode)
        _write_private(report_token_path, report_token.encode("utf-8"), 0o400)
        proxy: ScopedReadProxy | None = None
        proxy_socket: Path | None = None
        proxy_token_path: Path | None = None
        v3_entries: tuple[dict[str, str], ...] = ()
        if kind == "platform":
            read_key = spec.get("read_key_plaintext")
            scope = spec.get("platform_read_scope")
            if not isinstance(read_key, str) or not isinstance(scope, dict):
                report_sink.stop()
                raise CodexRuntimeError("Platform Examiner read proxy input is incomplete")
            forward = spec.get("platform_forwarder")
            if spec.get("formal_platform") is True and not callable(forward):
                report_sink.stop()
                raise CodexRuntimeError("formal Platform Examiner forwarder is unavailable")
            metrics = spec.get("_metrics")
            if callable(forward) and isinstance(metrics, ExaminerRunMetrics):
                raw_forward = forward

                def timed_forward(tool: str, arguments: Mapping[str, Any], key: str) -> Mapping[str, Any]:
                    started = time.monotonic()
                    try:
                        result = raw_forward(tool, arguments, key)
                        if isinstance(result, Mapping):
                            metrics.record_platform_response(result)
                        return result
                    finally:
                        metrics.record_proxy_time((time.monotonic() - started) * 1000)

                forward = timed_forward
            proxy_token = secrets.token_urlsafe(24)
            self._remember_secret(proxy_token.encode("utf-8"))
            self._remember_secret(read_key.encode("utf-8"))
            # Use the same short socket root selected for the report sink.  A
            # deep run path otherwise lets the report socket bind successfully
            # while the platform proxy fails with AF_UNIX's path-length limit.
            proxy_socket = socket_root / "platform-proxy.sock"
            proxy_token_path = home / "platform-proxy.token"
            v3_batch = batch_contract is not None
            if v3_batch:
                # One read-only scope entry per packet-authorized Ontology: the
                # packet binding supplies project/state identity, the Host's
                # pre-read supplies the default graph set, and the child may
                # select any subset per call.  Anything outside the list is
                # refused by the proxy before a forward.
                v3_entries = v3_proxy_scope_entries(
                    v3_packet,
                    spec.get("v3_graph_set_ids") or {},
                )
                proxy = ScopedReadProxy(
                    socket_path=proxy_socket,
                    token=proxy_token,
                    read_key=read_key,
                    authorized_ontologies=v3_entries,
                    ticket_digest=v3_ticket_digest(spec["ticket_digest"]),
                    model_state_digest=str(spec["model_state_digest"]),
                    allowed_tools=list(spec.get("allowed_read_tools") or ()),
                    forward=forward if callable(forward) else None,
                    acceptance_round_id=str(spec["acceptance_round_id"]),
                    child_handle_digest=str(spec["child_handle_digest"]),
                    exact_schemas=v3_examiner_proxy_schemas(
                        spec.get("allowed_read_tools") or ()
                    ),
                )
            else:
                proxy = ScopedReadProxy(
                    socket_path=proxy_socket,
                    token=proxy_token,
                    read_key=read_key,
                    project_id=str(scope.get("project_id")),
                    ontology_id=str(scope.get("ontology_id")),
                    graph_set_id=str(scope.get("graph_set_id")),
                    ticket_digest=str(spec["ticket_digest"]),
                    model_state_digest=str(spec["model_state_digest"]),
                    allowed_tools=list(spec.get("allowed_read_tools") or ()),
                    forward=forward if callable(forward) else None,
                    acceptance_round_id=str(spec["acceptance_round_id"]),
                    child_handle_digest=str(spec["child_handle_digest"]),
                    exact_schemas=examiner_proxy_schemas(spec.get("allowed_read_tools") or ()),
                )
            spec["_runtime_proxy"] = proxy
            proxy.start()
            # The proxy is the sole active holder of the temporary platform key.  Do not
            # retain the plaintext in the adapter/resource spec after proxy creation.
            spec.pop("read_key_plaintext", None)
            _write_private(proxy_token_path, proxy_token.encode("utf-8"), 0o400)
        config = {
            "kind": kind,
            "platform_proxy": proxy.receipt.__dict__ if proxy is not None else None,
            "report_sink": {"server": "examiner_report", "socket": "/agent/home/report.sock"},
            "descriptor": spec.get("descriptor"),
            "skill": {"name": skill.parent.name, "sha256": digest_file(skill)},
        }
        config_lines = [
            'sandbox_mode = "read-only"',
            'web_search = "disabled"',
            "[features]",
            "apps = false",
            "plugins = false",
            "multi_agent = false",
            "multi_agent_v2 = false",
            "browser_use = false",
            "computer_use = false",
            "image_generation = false",
            "memories = false",
            "hooks = false",
            "skill_search = false",
            "tool_suggest = false",
        ]
        if proxy is not None and proxy_socket is not None and proxy_token_path is not None:
            # Advisory env hints the child may show its model.  Legacy binds the
            # single authorized Ontology; v3 projects nothing per-Ontology,
            # because the packet-authorized scope is Host-owned and resolved per
            # call from the child's selection -- projecting the first entry here
            # is exactly the contradictory singleton that broke multi-Ontology
            # reads through the real bridge.
            if v3_entries:
                config_lines.extend(
                    [
                        "[mcp_servers.platform_read_proxy]",
                        'command = "/usr/bin/python3"',
                        'args = ["/agent/home/read_proxy_mcp.py", "--stdio", "--socket", "/agent/home/platform-proxy.sock", "--token-file", "/agent/home/platform-proxy.token"]',
                        "required = true",
                        "[mcp_servers.platform_read_proxy.env]",
                        f'PLATFORM_PROXY_MODE = {json.dumps(_V3_PROXY_BRIDGE_MODE)}',
                        "PLATFORM_PROXY_TICKET_DIGEST = "
                        + json.dumps(v3_ticket_digest(spec["ticket_digest"])),
                    ]
                )
            else:
                env_scope = {
                    "project_id": str(spec["platform_read_scope"]["project_id"]),
                    "ontology_id": str(spec["platform_read_scope"]["ontology_id"]),
                    "graph_set_id": str(spec["platform_read_scope"]["graph_set_id"]),
                    "ticket_digest": str(spec["ticket_digest"]),
                    "model_state_digest": str(spec["model_state_digest"]),
                }
                config_lines.extend(
                    [
                        "[mcp_servers.platform_read_proxy]",
                        'command = "/usr/bin/python3"',
                        'args = ["/agent/home/read_proxy_mcp.py", "--stdio", "--socket", "/agent/home/platform-proxy.sock", "--token-file", "/agent/home/platform-proxy.token"]',
                        "required = true",
                        "[mcp_servers.platform_read_proxy.env]",
                        f'PLATFORM_PROXY_PROJECT_ID = {json.dumps(env_scope["project_id"])}',
                        f'PLATFORM_PROXY_ONTOLOGY_ID = {json.dumps(env_scope["ontology_id"])}',
                        f'PLATFORM_PROXY_GRAPH_SET_ID = {json.dumps(env_scope["graph_set_id"])}',
                        f'PLATFORM_PROXY_TICKET_DIGEST = {json.dumps(env_scope["ticket_digest"])}',
                        f'PLATFORM_PROXY_MODEL_STATE_DIGEST = {json.dumps(env_scope["model_state_digest"])}',
                    ]
                )
        report_sink_args = [
            "/agent/home/report_sink_mcp.py",
            "--stdio",
            "--kind",
            kind,
            "--socket",
            "/agent/home/report.sock",
            "--token-file",
            "/agent/home/report-sink.token",
        ]
        if batch_contract is not None:
            # The child bridge repeats only the per-question field shape; batch
            # identity, order and completeness stay Host-side in the sink, so
            # the flags are convenience, never the enforcement boundary.
            report_sink_args.extend(
                [
                    "--schema",
                    batch_contract.schema_version,
                    "--batch-id",
                    batch_contract.batch_id,
                    "--role",
                    batch_contract.role,
                    "--question-ids",
                    ",".join(batch_contract.question_ids),
                ]
            )
        config_lines.extend(
            [
                "[mcp_servers.examiner_report]",
                'command = "/usr/bin/python3"',
                "args = ["
                + ", ".join(json.dumps(item) for item in report_sink_args)
                + "]",
                "required = true",
            ]
        )
        if formal:
            if not isinstance(child_model_override, RoleModelBinding):
                raise CodexRuntimeError("formal Examiner model binding is unavailable")
            if uses_external_credential_session(child_model_override.provider_id):
                sessions = self._provider_sessions
                if sessions is None:
                    raise CodexRuntimeError("formal provider sessions are unavailable")
                provider_lines = _formal_provider_config_lines(
                    child_model_override,
                    sessions.base_url_for(child_model_override.provider_id),
                )
            else:
                provider_lines = _formal_codex_builtin_config_lines(child_model_override)
                # The fresh child home performs the same thread/start models
                # lookup as a persistent role: seed its cache so the builtin
                # route cannot hit the online-refresh race (R2.3-008 R5-D1).
                self._seed_models_cache(home, child_model_override.model)
            config_lines = provider_lines[:3] + config_lines + provider_lines[3:]
        elif deepseek_enabled:
            provider_lines = _deepseek_provider_config_lines()
            config_lines = provider_lines[:3] + config_lines + provider_lines[3:]
        config_path = home / "config.toml"
        _write_private(config_path, ("\n".join(config_lines) + "\n").encode("utf-8"), 0o600)
        _write_private(home / "child-config.json", json.dumps(config, sort_keys=True, ensure_ascii=False).encode("utf-8"), 0o400)
        credential_manifest = {
            "key_id": spec.get("read_key_id") if kind == "platform" else None,
            "key_digest": spec.get("read_key_digest") if kind == "platform" else None,
            "project_id": spec.get("platform_read_scope", {}).get("project_id") if kind == "platform" else None,
            "ontology_id": spec.get("platform_read_scope", {}).get("ontology_id") if kind == "platform" else None,
            "ticket_digest": spec.get("ticket_digest"),
            "acceptance_round_id": spec.get("acceptance_round_id"),
            "child_input_digest": spec.get("input_digest"),
            "config_digest": child_config_digest(
                {
                    "kind": kind,
                    "allowlist": list(spec.get("allowed_read_tools", ())),
                    "scope": spec.get("platform_read_scope"),
                }
            ) if kind == "platform" else None,
            "proxy": proxy.receipt.__dict__ if proxy is not None else None,
        }
        if batch_contract is not None:
            # v3 authorizes a list of Ontologies; record it explicitly so the
            # manifest still describes the exact read scope granted to the child.
            credential_manifest["authorized_ontology_ids"] = [
                entry["ontology_id"] for entry in v3_entries
            ]
            credential_manifest["project_id"] = v3_entries[0]["project_id"] if v3_entries else None
            credential_manifest["ontology_id"] = None
        _write_private(home / "child-credential-manifest.json", json.dumps(credential_manifest, sort_keys=True, ensure_ascii=False).encode("utf-8"), 0o400)
        descriptor_payload = {
            "kind": str(spec.get("descriptor", {}).get("kind", f"{kind}_examiner")),
            "package_digest": str(spec.get("descriptor", {}).get("package_digest", "")),
            "platform_mode": "read" if kind == "platform" else "none",
            "can_team_transport": False,
            "can_spawn": False,
            "can_write": False,
            "max_children": 0,
        }
        _write_private(descriptor_path, json.dumps(descriptor_payload, sort_keys=True).encode("utf-8"), 0o400)
        _write_private(home / "read_proxy_mcp.py", (self.root / "modeling_team" / "read_proxy_mcp.py").read_bytes(), 0o444)
        _write_private(home / "report_sink_mcp.py", (self.root / "modeling_team" / "report_sink_mcp.py").read_bytes(), 0o444)
        command = self._acceptance_namespace_command(
            home=home,
            work=work,
            skills=skills,
            proxy_socket=proxy_socket,
            report_socket=report_socket,
        )
        # Formal proxy authentication is deliberately absent from process env.
        env = _minimal_codex_process_env(home, deepseek_key)
        process = self.process_factory(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
            cwd=str(work),
            env=env,
        )
        resource = _CodexChildResource(
            spec,
            process,
            proxy=proxy,
            report_sink=report_sink,
            startup_complete=False,
        )
        spec["_runtime_resource"] = resource
        spec.pop("_runtime_proxy", None)
        spec.pop("_runtime_report_sink", None)
        child_package = AgentPackage(
            package_id=f"{kind}-examiner" if kind != "acceptance" else "acceptance",
            role=(
                "source-specialist"
                if kind == "source"
                else "platform-specialist"
                if kind == "platform"
                else "acceptance"
            ),
            description=f"Private {kind} Examiner",
            instructions_path=home / "instructions.md",
            required_skills=(skills / skill.parent.name / "SKILL.md",),
            references=(),
            permissions={"team_transport": False, "platform": "read" if kind == "platform" else "none", "source": "read" if kind == "source" else "none", "spawn": False, "write": False},
            runtime={
                "codex": {
                    "sandbox": "read-only",
                    **(
                        {
                            "model": child_model_override.model,
                            "model_provider": child_model_override.provider_id,
                            "model_reasoning_effort": child_model_override.effective_effort,
                            # Route identity stays ``openai-codex``; only the
                            # fixed safe auth-mode label is projected here.
                            **(
                                {"auth_mode": CODEX_AUTH_MODE}
                                if formal_codex_builtin
                                else {}
                            ),
                        }
                        if isinstance(child_model_override, RoleModelBinding)
                        else {}
                    ),
                }
            },
            task_input={},
        )
        child_agent = _Agent(
            f"{kind}-examiner-{str(spec['child_handle_digest'])[:8]}",
            child_package,
            home,
            work,
            skills,
            process=process,
            platform_tools=frozenset(spec.get("allowed_read_tools", ())) if kind == "platform" else frozenset(),
        )
        # Formal external-route children ride the loopback provider proxy
        # (barrier is a marker only); formal ``openai-codex`` children carry the
        # staged ChatGPT login cache, which the barrier unlinks before any
        # model-selected dispatch.  Non-formal children keep file auth.
        child_agent.auth_path = (
            home / "auth.json" if (not formal or formal_codex_builtin) else None
        )
        child_agent.auth_barrier_pending = formal
        child_agent.credential_mode = (
            "provider_proxy" if (formal and not formal_codex_builtin) else "file_auth"
        )
        if formal:
            self._start_stderr_drain(child_agent)
        # Bind the resource to the child even before stdout-pump startup so an
        # initialize/thread failure can stop the drain during unwind.
        resource._adapter = self
        resource._child_agent = child_agent
        try:
            self._rpc(child_agent, "initialize", {"clientInfo": {"name": "modeling-team-examiner", "version": "1"}})
            thread_start_params = {
                "cwd": "/agent/work",
                "baseInstructions": "",
                "developerInstructions": instructions.read_text(encoding="utf-8"),
                "config": {"web_search": "disabled", "default_tools_enabled": False},
                "sandbox": "read-only",
            }
            if formal:
                # The child Thread must use the exact model selected for its
                # predeclared Examiner package.  Provider/reasoning stay in the
                # profile-backed TOML written above; non-formal child fixtures keep
                # their historical request shape.
                thread_start_params["model"] = child_model_override.model
            thread_result = self._rpc(child_agent, "thread/start", thread_start_params)
            thread = thread_result.get("thread", thread_result) if isinstance(thread_result, dict) else {}
            thread_id = thread.get("id") if isinstance(thread, dict) else None
            if not isinstance(thread_id, str) or not thread_id:
                raise CodexRuntimeError("Examiner thread/start lacked Thread identity")
            # The child must discover the exact local MCP inventory before any model
            # turn.  This makes a missing/extra wrapper a startup contract failure,
            # rather than an ambiguous semantic report.
            child_agent.thread_id = thread_id
            if bool(spec.get("lean_examiner")):
                self._require_lean_examiner_mcp_servers(child_agent)
            else:
                self._require_expected_mcp_servers(child_agent)
            first_turn_input = spec.get("first_turn_input")
            if not isinstance(first_turn_input, list) or not first_turn_input:
                first_turn_input = [
                    {
                        "type": "text",
                        "text": (
                            "Read only /agent/home/input.json. Call the MCP tool "
                            "submit_examiner_report with one bounded terminal report. If the "
                            "sink rejects it, correct the report from the returned detail and "
                            "resubmit without issuing further proxy reads; do not use raw "
                            "sockets or any other capability."
                        )
                        # The formal Source child's input.json is a path/digest
                        # projection without source bytes; SOURCE_TEXT_JSON is
                        # its only legitimate channel to the approved text (the
                        # lean path pioneered this seam; see the staging block).
                        + source_text_json,
                    }
                ]
            turn_result = self._rpc(child_agent, "turn/start", {"threadId": thread_id, "input": first_turn_input})
            resource.thread_id = thread_id
            resource.first_turn_input = first_turn_input
            metrics = spec.get("_metrics")
            if not isinstance(metrics, ExaminerRunMetrics) or metrics.role != kind:
                metrics = ExaminerRunMetrics(kind)
            metrics.bind_thread(thread_id)
            metrics.record_turn_start()
            packet = spec.get("_packet")
            metrics.bind_first_turn_input(
                first_turn_input,
                packet=packet if isinstance(packet, ExaminerRolePacket) else None,
            )
            resource.metrics = metrics
            resource.spec["turn_id"] = self._turn_id(turn_result)
            resource.spec["proxy_receipt"] = proxy.receipt.__dict__ if proxy is not None else None
            resource.spec["config_digest"] = child_config_digest(
                {
                    "kind": kind,
                    "allowlist": list(spec.get("allowed_read_tools", ())),
                    "scope": spec.get("platform_read_scope"),
                }
            )
            resource.spec["runtime_config_digest"] = child_config_digest(config)
            resource.submitted_reports = submitted_reports
            resource.startup_complete = True
            # The Examiner child is intentionally not registered in
            # ``self.agents``, so the persistent-role output drains never cover it.
            # Formal Acceptance defers this pump until the carrier has registered
            # the resource and validated any report that arrived during startup;
            # direct/non-formal fixtures retain immediate startup.
            if not bool(spec.get("defer_output_pump")):
                resource.start_stdout_pump(self, child_agent)
            return resource
        except Exception as exc:
            resource.failure_category = "runtime"
            resource.failure_reason = "child-start-failed"
            resource.destroy()
            raise CodexRuntimeError("Examiner child startup failed") from exc

    @staticmethod
    def _write_child_private(path: Path, payload: bytes, mode: int) -> None:
        if path.is_symlink() or path.exists():
            raise CodexRuntimeError("Examiner private artifact already exists")
        path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())

    @staticmethod
    def _unlink_private_auth(home: Path) -> None:
        """Remove staged provider auth after init/MCP discovery, before first turn."""

        auth = home / "auth.json"
        try:
            auth.unlink(missing_ok=True)
        except OSError as exc:
            raise CodexRuntimeError("private provider auth cleanup failed") from exc

    @staticmethod
    def _is_formal_acceptance_run(run: Any) -> bool:
        if getattr(run, "formal_contract", None) is not None:
            return True
        configuration = getattr(run, "configuration", None)
        task = getattr(configuration, "task", None)
        profile = getattr(configuration, "profile", None)
        return bool(
            getattr(task, "schema_version", 1) == 2
            and (
                getattr(task, "task_id", None)
                in {
                    "r2-3-005-formal-acceptance",
                    "r2-3-003-existing-scope-incremental",
                }
                or getattr(profile, "profile_id", None)
                in {"r2-3-005-modeling-team", "r2-3-003-modeling-team"}
            )
        )

    @staticmethod
    def _is_r23003_run(run: Any) -> bool:
        contract = getattr(run, "formal_contract", None)
        if contract is not None:
            return getattr(contract, "requirement_id", None) == "R2.3-003"
        configuration = getattr(run, "configuration", None)
        task = getattr(configuration, "task", None)
        profile = getattr(configuration, "profile", None)
        return bool(
            getattr(task, "task_id", None) == "r2-3-003-existing-scope-incremental"
            or getattr(profile, "profile_id", None) == "r2-3-003-modeling-team"
        )

    @staticmethod
    def _is_multi_slice_run(run: Any) -> bool:
        """R3.0-002: a v2 Task declaring ``multi_slice_workflow: true``."""

        task = getattr(getattr(run, "configuration", None), "task", None)
        if getattr(task, "schema_version", 1) != 2:
            return False
        parameters = getattr(task, "parameters", None)
        return isinstance(parameters, dict) and parameters.get("multi_slice_workflow") is True

    @staticmethod
    def _is_staged_decisions_run(run: Any) -> bool:
        """R3.0-008B: a v2 Task declaring ``staged_modeling_decisions: true``."""

        task = getattr(getattr(run, "configuration", None), "task", None)
        if getattr(task, "schema_version", 1) != 2:
            return False
        parameters = getattr(task, "parameters", None)
        return isinstance(parameters, dict) and parameters.get("staged_modeling_decisions") is True

    @staticmethod
    def _is_unified_graph_run(run: Any) -> bool:
        """R3.0-009: a v2 Task declaring ``unified_semantic_graph: true``.

        Same predicate shape and same Task-parameter source as the Runner's
        ``TeamRunner._unified_graph`` flag, so the Adapter mount table and the
        Runner artifact schema dispatch can never disagree about the mode.
        """

        task = getattr(getattr(run, "configuration", None), "task", None)
        if getattr(task, "schema_version", 1) != 2:
            return False
        parameters = getattr(task, "parameters", None)
        return isinstance(parameters, dict) and parameters.get("unified_semantic_graph") is True

    @staticmethod
    def _is_competency_question_run(run: Any) -> bool:
        """R3.0-011: a v2 Task declaring ``competency_question_acceptance: true``."""

        task = getattr(getattr(run, "configuration", None), "task", None)
        if getattr(task, "schema_version", 1) != 2:
            return False
        parameters = getattr(task, "parameters", None)
        return (
            isinstance(parameters, dict)
            and parameters.get("competency_question_acceptance") is True
        )

    def _competency_questions_enabled_for_active_run(self, run: Any | None) -> bool:
        """CQ stage flag with the active-run fallback for late callers."""

        candidate = run if run is not None else getattr(self, "_active_run", None)
        return self._is_competency_question_run(candidate)

    @classmethod
    def _candidate_platform_gate_enabled_for_run(cls, run: Any) -> bool:
        """One predicate for BOTH gate wiring points (design increment 7).

        The MCP env passing point (``_write_config``) and the sandbox
        bind-mount point (``_candidate_platform_gate_enabled`` assignment in
        ``start_roster`` plus the mount block in ``namespace_command``) must
        derive from this single predicate: extending only one of the two
        leaves the in-sandbox gate state file unreachable and every backend
        MCP platform call fails closed forever (plan review High-4).
        """

        configuration = getattr(run, "configuration", None)
        task = getattr(configuration, "task", None)
        if getattr(task, "schema_version", 1) != 2:
            return False
        return cls._is_formal_acceptance_run(run) or cls._is_multi_slice_run(run)

    @staticmethod
    def _proof_gate_enabled(run: Any) -> bool:
        """Resolve proof-v2 assets from an explicit gate, not schema version alone.

        A missing or null binding is non-proof.  Real TeamRun instances carry the
        marker, so a non-null binding is the only normal proof gate; the archived
        P2a production task remains an explicit proof-gated overlay.
        """
        gate_binding = getattr(run, "gate_binding", None)
        configuration = getattr(run, "configuration", None)
        task = getattr(configuration, "task", None)
        profile = getattr(configuration, "profile", None)
        expected_binding = getattr(task, "expected_matrix_binding", None) or getattr(
            profile, "expected_matrix_binding", None
        )
        return (
            gate_binding is not None
            or expected_binding is not None
            or getattr(task, "task_id", None) == "p2a-protocol-production"
        )

    def _role_capability_operations(self, role: str, *, run: Any | None = None) -> tuple[str, ...]:
        """Return only capabilities actually configured for this formal run.

        R3.0-008B: a staged (non-formal) run additionally advertises the staged
        Modeling Batch submission operation to the protocol role.  The
        formal-run expression below is unchanged (it considers only the
        explicit ``run`` argument); staged advertisement is a separate branch
        keyed on the active run, so non-staged assemblies stay byte-identical.
        """

        formal_run = self._coordination_enabled or (
            run is not None and self._is_formal_acceptance_run(run)
        )
        if not formal_run or self._acceptance is None:
            if (
                role == "protocol"
                and not formal_run
                and self._staged_decisions_enabled_for_active_run(run)
            ):
                # Staged non-formal protocol: only the staged submission
                # operation; the formal protocol set stays formal-only.
                return (STAGED_PROTOCOL_OPERATION,)
            if (
                role == COMPETENCY_QUESTION_ROLE
                and not formal_run
                and self._competency_questions_enabled_for_active_run(run)
            ):
                # R3.0-011: the competency-question role owns exactly one
                # Runner-private capability and no platform tool at all.
                return (CQ_OPERATION,)
            return ()
        expected = ROLE_OPERATIONS.get(role, ())
        if not hasattr(self._acceptance, "capability_descriptors"):
            # Keep lightweight Runtime test doubles and legacy adapters
            # compatible; a real RunnerAcceptanceCarrier always exposes the
            # descriptor map and therefore takes the authoritative path below.
            return expected if role != "modeling" else ()
        descriptors = getattr(self._acceptance, "capability_descriptors", None)
        if not isinstance(descriptors, dict):
            return ()
        descriptor = descriptors.get(role)
        operations = descriptor.get("operations") if isinstance(descriptor, dict) else None
        if not isinstance(operations, list) or any(not isinstance(item, str) for item in operations):
            return ()
        normalized = tuple(operations)
        if not normalized or len(set(normalized)) != len(normalized):
            return ()
        return normalized if set(normalized).issubset(expected) else ()

    def _staged_decisions_enabled_for_active_run(self, run: Any | None) -> bool:
        """Staged decisions flag with the active-run fallback for late callers.

        Elicititation allowlists and expected-server checks call
        ``_role_capability_operations(role)`` without an explicit run; the
        active run captured by ``start_roster`` answers for them.
        """

        candidate = run if run is not None else getattr(self, "_active_run", None)
        return self._is_staged_decisions_run(candidate)

    @staticmethod
    def preflight_host_auth() -> Path:
        """Validate the host auth source without opening or emitting its contents."""
        host_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        host_auth = host_home / "auth.json"
        try:
            metadata = os.lstat(host_auth)
        except OSError as exc:
            raise CodexRuntimeError("host Codex authentication is unavailable for private staging") from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise CodexRuntimeError("host Codex authentication is unavailable for private staging")
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
            raise CodexRuntimeError("host Codex authentication is not owner-private")
        return host_auth

    def _resolve_deepseek_api_key(self) -> str:
        """Resolve the provider key without retaining it in any generated artifact.

        The process environment is the primary Host-owned source.  The repository
        fallback is deliberately narrow: it must be a user-owned, non-symlink,
        private regular file and contain one exact ``LLM_API_KEY=value`` assignment.
        """

        process_value = os.environ.get(_DEEPSEEK_API_KEY_ENV)
        if process_value is not None:
            if (
                not process_value
                or not process_value.strip()
                or process_value != process_value.strip()
                or any(char in process_value for char in "\x00\r\n")
            ):
                self._adapter._stderr_drain_reports[self._child_agent.agent_id] = (
                    self._child_agent.stderr_drain.snapshot()
                )
                raise CodexRuntimeError("DeepSeek API key is missing or malformed")
            return process_value

        fallback = self.root / "backend" / ".env"
        try:
            metadata = os.lstat(fallback)
        except OSError as exc:
            raise CodexRuntimeError("DeepSeek API key is unavailable") from exc
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            raise CodexRuntimeError("DeepSeek fallback file is insecure")
        try:
            content = fallback.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise CodexRuntimeError("DeepSeek fallback file is malformed") from exc

        matches: list[str] = []
        for line in content.splitlines():
            if not line or line.lstrip().startswith("#"):
                continue
            match = re.fullmatch(r"LLM_API_KEY=([^=\s\r\n\"']+)", line)
            if match:
                matches.append(match.group(1))
                continue
            if re.match(r"^\s*(?:export\s+)?LLM_API_KEY\b", line):
                raise CodexRuntimeError("DeepSeek fallback assignment is malformed")
        if len(matches) != 1 or not matches[0].strip():
            raise CodexRuntimeError("DeepSeek API key is unavailable")
        return matches[0]

    def _lifecycle_has_active_resources(self) -> bool:
        """Return whether a prior lifecycle still owns live process resources."""

        if self._acceptance_children:
            return True
        for agent in self.agents.values():
            process = agent.process
            if process is None:
                continue
            poll = getattr(process, "poll", None)
            try:
                if callable(poll) and poll() is None:
                    return True
                if not callable(poll):
                    return True
            except Exception:
                return True
        sessions = self._provider_sessions
        if sessions is not None:
            try:
                if sessions.listening():
                    return True
            except Exception:
                return True
        return False

    def start_roster(self, run: Any, agents: Any) -> list[AgentRuntimeIdentity]:
        with self._cleanup_lock:
            if self._lifecycle_has_active_resources():
                raise CodexRuntimeError("runtime lifecycle still owns active resources")
            if self._cleanup_snapshot is not None and self._cleanup_errors and self._coordination_enabled:
                raise CodexRuntimeError("previous formal cleanup failed")
            # A completed cleanup starts a fresh lifecycle.  The previous
            # immutable snapshot remains available to callers that already
            # captured it, while this adapter's next run receives clean state.
            self._cleanup_snapshot = None
            self._formal_cleanup_aggregate = None
            self._cleanup_errors.clear()
            self._provider_stop_status.clear()
            self.agents.clear()
            self._acceptance_children.clear()
            self._run_root = run.root
            self._run_id = run.run_id
            self._active_run = run
            self._secret_audit_values.clear()
            self._secret_audit_failures.clear()
            self._private_credentials_destroyed.clear()
            self._stderr_drain_failures.clear()
            self._stderr_drain_reports.clear()
            self._provider_session_failure_latched = False
            self._child_auth_barriers.clear()
            with self._runtime_failure_lock:
                self._runtime_failures.clear()
            with self._inactivity_lock:
                self._inactivity_failures.clear()
        self._acceptance = getattr(run, "acceptance", None)
        self._coordination_enabled = self._is_formal_acceptance_run(run)
        self._team_model_profile = (
            getattr(run, "team_model_profile", None)
            if self._coordination_enabled
            else None
        )
        if self._coordination_enabled and not isinstance(
            self._team_model_profile, TeamModelProfile
        ):
            raise CodexRuntimeError("formal runtime model profile is unavailable")
        if self._coordination_enabled:
            external_provider_ids = tuple(
                provider_id
                for provider_id in self._team_model_profile.provider_ids()
                if uses_external_credential_session(provider_id)
            )
            if external_provider_ids:
                # One loopback session per external credential-backed provider
                # the profile actually references, shared by all roles on that
                # provider.  Startup re-opens each credential with the
                # no-follow/revalidation contract; failures are typed and leave
                # no session behind.  An OpenAI-only profile creates no
                # manager: ``openai-codex`` rides Codex's built-in route with
                # the staged Host ChatGPT login instead.
                credential_bindings = getattr(run, "provider_credential_bindings", None)
                if not isinstance(credential_bindings, Mapping) or not credential_bindings:
                    raise CodexRuntimeError(
                        "formal provider credential bindings are unavailable"
                    )
                try:
                    sessions = ProviderSessionManager(
                        credential_bindings,
                        on_failure=self._on_provider_session_failure,
                    )
                    sessions.start()
                except Exception as exc:
                    with self._runtime_failure_lock:
                        self._runtime_failures.append(
                            (
                                "provider-sessions",
                                {
                                    "category": "runtime/infrastructure",
                                    "reason_code": "provider-session-start-failed",
                                },
                            )
                        )
                    raise CodexRuntimeError(
                        "formal provider session startup failed"
                    ) from exc
                self._provider_sessions = sessions
        # R3.0-002: derive the sandbox bind-mount gate flag from the same
        # single predicate as the MCP env point in ``_write_config`` (formal
        # acceptance OR multi_slice_workflow, both v2-only).
        self._candidate_platform_gate_enabled = (
            self._candidate_platform_gate_enabled_for_run(run)
        )
        # R3.0-006 start3 narrow repair: the Coordinator owns the run-root
        # scenario-map artifacts (R3.0-002 §3.2) but its frozen package sandbox
        # is read-only and the run root is otherwise unmounted in every Agent
        # namespace, so no role can create ``scenario-map/`` files.  For
        # multi-slice runs only, ``namespace_command`` binds exactly that one
        # directory writable at the cwd-relative path the frozen instructions
        # name, and the thread sandbox is raised to workspace-write.
        self._multi_slice_scenario_map_enabled = self._is_multi_slice_run(run)
        # R3.0-008B: staged modeling decision binds/advertisement are keyed on
        # the task parameter; every non-staged run keeps its exact previous
        # bind set and capability operations.
        self._staged_decisions_enabled = self._is_staged_decisions_run(run)
        # R3.0-009: unified mode is an opt-in extension of the staged
        # decisions path and only changes the stage3 mount split.
        self._unified_graph = self._is_unified_graph_run(run)
        self._formal_turn_binding_required = self._coordination_enabled
        parameters = getattr(getattr(getattr(run, "configuration", None), "profile", None), "parameters", None)
        if isinstance(parameters, Mapping):
            try:
                self._inactivity_timeout_seconds = float(
                    parameters.get("llm_inactivity_timeout_seconds", _LLM_INACTIVITY_TIMEOUT_SECONDS)
                )
            except (TypeError, ValueError):
                self._inactivity_timeout_seconds = _LLM_INACTIVITY_TIMEOUT_SECONDS
        # Formal model authentication never resolves the historical DeepSeek
        # environment key here: a sentinel in the Host environment must have no
        # formal effect.  External-route roles ride the loopback provider
        # sessions; ``openai-codex`` roles get their private staged auth.json
        # during app-server initialization only (see ``_write_config``).
        identities: list[AgentRuntimeIdentity] = []
        scope = getattr(run, "scope", {})
        scope_mode = scope.get("mode") if isinstance(scope, dict) else getattr(scope, "mode", None)
        for profile_agent in agents:
            package = profile_agent.package
            base = run.root / "runtime" / profile_agent.agent_id
            home, work, skills = base / "home", base / "work", base / "skills"
            for path in (home, work, skills):
                path.mkdir(parents=True, mode=0o700, exist_ok=False)
            tools = (
                frozenset()
                # R3.0-011: the competency-question role has no platform tool at
                # all; its only capability is the Runner-private draft channel.
                if package.role == COMPETENCY_QUESTION_ROLE
                else frozenset(run.configuration.task.protocol_tools)
                if package.role == "protocol" and run.configuration.task.schema_version == 2
                else frozenset(MODELING_READ_TOOLS)
                if package.role == "modeling" and self._is_r23003_run(run)
                else frozenset()
                if package.role == "acceptance"
                else frozenset({"check_platform_health"})
            )
            agent = _Agent(
                profile_agent.agent_id,
                package,
                home,
                work,
                skills,
                platform_tools=tools,
                schema_version=run.configuration.task.schema_version,
                proof_gate=self._proof_gate_enabled(run),
                fallback_eligible=(
                    package.role == "protocol"
                    and run.configuration.task.schema_version == 2
                    and scope_mode == "create"
                ),
            )
            self.agents[agent.agent_id] = agent
            try:
                self._stage_protocol_mechanics_contract(run, agent)
                self._stage_protocol_retrieval_mcp(run, agent)
                self._stage_skills(agent)
                self._write_config(run, agent)
                agent.process = self._start_process(agent)
                self._initialize(agent)
            except Exception:
                self._cleanup_startup_auth(agent)
                # Unwind any already-started roles, children, and the shared
                # provider proxy before exposing a startup failure.
                self.stop()
                raise
            agent.app_server_host_pid = self._app_server_host_pid(agent)
            with agent.state_lock:
                agent.last_output_monotonic = time.monotonic()
            self._start_inactivity_watchdog(agent)
            identities.append(
                AgentRuntimeIdentity(agent.agent_id, f"codex-thread:{agent.thread_id}")
            )
        return identities

    @staticmethod
    def _cleanup_startup_auth(agent: _Agent) -> None:
        if agent.credential_mode == "provider_proxy":
            agent.auth_barrier_pending = False
            return
        path = agent.auth_path
        if path is None:
            return
        try:
            path.unlink(missing_ok=True)
        except OSError:
            # The outer Runner cleanup/audit remains authoritative if a startup
            # failure races an OS-level unlink error.
            pass
        agent.auth_barrier_pending = False

    def _reset_activity_clock(self, agent: _Agent) -> None:
        """Mark now as the last observed App Server activity (inactivity clock origin).

        Safe for test doubles that omit ``state_lock``: a single float store is atomic
        under the CPython GIL, so the watchdog's read never observes a torn value.
        """
        now = time.monotonic()
        lock = getattr(agent, "state_lock", None)
        if lock is None:
            agent.last_output_monotonic = now
            return
        with lock:
            agent.last_output_monotonic = now

    def _start_inactivity_watchdog(self, agent: _Agent) -> None:
        """Start a per-role daemon thread that fails fast on a hung model endpoint.

        Mirrors the Examiner child watchdog but is an inactivity timer: while the role
        is in a running turn, absence of any App Server notification for
        ``_inactivity_timeout_seconds`` means the model endpoint (or the App Server) is
        hung.  The thread never blocks the main loop; it only latches a failure, kills
        the role process group, and queues the failure for ``runner.drain`` to settle.
        """
        timeout = self._inactivity_timeout_seconds

        def watch() -> None:
            while not agent.inactivity_watchdog_stop.wait(0.05):
                with agent.state_lock:
                    state = agent.state
                    last = agent.last_output_monotonic
                    already_failed = getattr(agent, "runtime_failure", None) is not None
                if already_failed or state != "running" or last <= 0.0:
                    continue
                if time.monotonic() - last >= timeout:
                    self._on_inactivity_timeout(agent, timeout)
                    return

        thread = threading.Thread(
            target=watch,
            name=f"role-inactivity-watchdog-{agent.agent_id}",
            daemon=True,
        )
        agent.inactivity_watchdog_thread = thread
        thread.start()

    @staticmethod
    def _safe_runtime_detail(agent: _Agent, detail: Mapping[str, Any]) -> dict[str, Any]:
        """Project one failure to the fixed, provider-text-free evidence shape."""

        safe: dict[str, Any] = {
            "agent_id": agent.agent_id,
            "role": str(getattr(agent.package, "role", agent.agent_id)),
        }
        for key in (
            "source",
            "reason",
            "variant",
            "turn_digest",
            "terminal_method",
        ):
            value = detail.get(key)
            if isinstance(value, str) and value and len(value) <= 128:
                safe[key] = value
        for key in ("will_retry", "timeout_seconds", "idle_seconds", "http_status"):
            value = detail.get(key)
            if key == "will_retry":
                if isinstance(value, bool):
                    safe[key] = value
            elif key == "http_status":
                if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 65535:
                    safe[key] = value
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                safe[key] = value
        return safe

    def _terminate_runtime_process_once(self, agent: _Agent) -> None:
        """Terminate one role process group at most once after a typed failure."""

        lock = getattr(agent, "state_lock", None)
        if lock is None:
            if getattr(agent, "runtime_failure_termination_attempted", False):
                return
            agent.runtime_failure_termination_attempted = True
        else:
            with lock:
                if getattr(agent, "runtime_failure_termination_attempted", False):
                    return
                agent.runtime_failure_termination_attempted = True
        process = agent.process
        if process is None:
            return
        pid = getattr(process, "pid", None)
        try:
            if isinstance(pid, int) and pid > 0:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            else:
                terminate = getattr(process, "terminate", None)
                if callable(terminate):
                    terminate()
        except (ProcessLookupError, PermissionError, OSError):
            # The cleanup owner performs the final process wait/kill.  This latch
            # only needs to prevent a duplicate termination attempt.
            pass

    def _latch_runtime_failure(
        self,
        agent: _Agent,
        detail: Mapping[str, Any],
        *,
        evidence_type: str = "runtime-failure",
        compatibility_inactivity: bool = False,
    ) -> bool:
        """Latch and queue one sanitized runtime failure, idempotently."""

        safe = self._safe_runtime_detail(agent, detail)
        lock = getattr(agent, "state_lock", None)
        if lock is None:
            if getattr(agent, "runtime_failure", None) is not None:
                return False
            agent.runtime_failure = safe
            if compatibility_inactivity:
                agent.inactivity_failure = dict(safe)
            agent.state = "failed"
        else:
            with lock:
                if getattr(agent, "runtime_failure", None) is not None:
                    return False
                agent.runtime_failure = safe
                if compatibility_inactivity:
                    agent.inactivity_failure = dict(safe)
                agent.state = "failed"
        self._terminate_runtime_process_once(agent)
        self._append_runtime_evidence(evidence_type, safe)
        with self._runtime_failure_lock:
            self._runtime_failures.append((agent.agent_id, dict(safe)))
        return True

    def _on_inactivity_timeout(self, agent: _Agent, timeout: float) -> None:
        """Latch one inactivity failure, kill the role process, and queue for drain."""

        with agent.state_lock:
            if agent.runtime_failure is not None or agent.inactivity_watchdog_stop.is_set():
                return
            now = time.monotonic()
            idle_seconds = (
                (now - agent.last_output_monotonic)
                if agent.last_output_monotonic
                else timeout
            )
        detail = {
            "source": "inactivity-watchdog",
            "timeout_seconds": timeout,
            "idle_seconds": idle_seconds,
            "reason": "llm-inactivity-timeout",
        }
        if not self._latch_runtime_failure(
            agent,
            detail,
            evidence_type="llm-inactivity-timeout",
            compatibility_inactivity=True,
        ):
            return
        # The historical reader remains a compatibility projection for callers
        # that predate the typed runtime queue.  Runner prefers the generic queue.
        with self._inactivity_lock:
            self._inactivity_failures.append((agent.agent_id, dict(agent.inactivity_failure or {})))

    def consume_runtime_failures(self) -> list[tuple[str, dict[str, Any]]]:
        """Return and clear typed provider/watchdog failures exactly once."""

        with self._runtime_failure_lock:
            failures = self._runtime_failures
            self._runtime_failures = []
        return failures

    def consume_inactivity_failures(self) -> list[tuple[str, dict[str, Any]]]:
        """Return and clear latched role inactivity failures (called by ``runner.drain``)."""

        with self._inactivity_lock:
            failures = self._inactivity_failures
            self._inactivity_failures = []
        return failures

    @staticmethod
    def _stage_protocol_mechanics_contract(run: Any, agent: _Agent) -> None:
        """Publish the v2 Protocol-only mechanics asset outside every Agent home."""
        task = getattr(getattr(run, "configuration", None), "task", None)
        if agent.package.role != "protocol" or getattr(task, "schema_version", 1) != 2:
            return
        run_id = getattr(run, "run_id", None)
        if not isinstance(run_id, str) or not run_id:
            raise CodexRuntimeError("v2 Protocol mechanics contract requires a run ID")
        assets = run.root / "runtime-assets"
        protocol_assets = assets / "protocol"
        protocol_assets.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(assets, 0o700)
        os.chmod(protocol_assets, 0o700)
        contract = protocol_assets / "mechanics-contract.json"
        try:
            descriptor = os.open(contract, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        except FileExistsError as exc:
            raise CodexRuntimeError("v2 Protocol mechanics contract already exists") from exc
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(protocol_mechanics_contract_bytes(run_id))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(contract, 0o444)
        agent.mechanics_contract_path = contract

    def _stage_protocol_retrieval_mcp(self, run: Any, agent: _Agent) -> None:
        """Stage the sole v2 Protocol retrieval MCP wrapper and verifier as immutable assets."""
        task = getattr(getattr(run, "configuration", None), "task", None)
        if agent.package.role != "protocol" or getattr(task, "schema_version", 1) != 2:
            return
        agent.proof_gate = self._proof_gate_enabled(run)
        assets = run.root / "runtime-assets" / "protocol"
        assets.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(assets.parent, 0o700)
        os.chmod(assets, 0o700)
        for directory in (assets.parent, assets):
            metadata = os.lstat(directory)
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISDIR(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o700
                or metadata.st_uid != os.getuid()
            ):
                raise CodexRuntimeError("Protocol retrieval MCP asset directory is invalid")
        wrapper = assets / "protocol-retrieval-mcp.py"
        verifier = assets / "protocol_mechanics.py"
        proof_v2 = assets / "proof_v2.py"
        source_specs = [
            (wrapper, self.root / "modeling_team" / "protocol_retrieval_mcp.py", "protocol_retrieval_mcp", 0o444),
            (verifier, self.root / "modeling_team" / "protocol_mechanics.py", "protocol_retrieval_verifier", 0o444),
        ]
        if agent.proof_gate:
            source_specs.append(
                (proof_v2, self.root / "modeling_team" / "proof_v2.py", "proof_v2", 0o600)
            )
        baseline_path = run.root / "baseline-manifest.json"
        baseline = json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.exists() else {}
        expected_digests = baseline.get("files", {}) if isinstance(baseline, dict) else {}
        for target, source, baseline_key, mode in source_specs:
            try:
                metadata = os.lstat(source)
            except OSError as exc:
                raise CodexRuntimeError("Protocol retrieval MCP source is unavailable") from exc
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
            ):
                raise CodexRuntimeError("Protocol retrieval MCP source is invalid")
            if expected_digests and expected_digests.get(baseline_key) != digest_file(source):
                raise CodexRuntimeError("Protocol retrieval MCP source drifts from baseline")
            try:
                descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
            except FileExistsError as exc:
                raise CodexRuntimeError("Protocol retrieval MCP asset already exists") from exc
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(source.read_bytes())
                    stream.flush()
                    os.fsync(stream.fileno())
            except Exception:
                target.unlink(missing_ok=True)
                raise
            os.chmod(target, mode)
            staged = os.lstat(target)
            if (
                stat.S_ISLNK(staged.st_mode)
                or not stat.S_ISREG(staged.st_mode)
                or stat.S_IMODE(staged.st_mode) != mode
                or staged.st_uid != os.getuid()
            ):
                raise CodexRuntimeError("Protocol retrieval MCP staged asset metadata is invalid")
        agent.retrieval_mcp_path = wrapper
        agent.retrieval_verifier_path = verifier
        agent.proof_v2_path = proof_v2 if agent.proof_gate else None

    def probe_role_visibility(self, run: Any) -> dict[str, Any]:
        """Run only path-readability probes inside each Agent's own bwrap namespace."""
        if not self.use_bwrap:
            raise CodexRuntimeError("visibility probes require bubblewrap isolation")
        result: dict[str, Any] = {}
        forbidden_common = (
            "/home/yangxiang/projects/ontology-platform",
            "/agent/home/sources/../../protocol/home",
            "/agent/home/sources/docs/requirements/requirements-v2.3.md",
            "/agent/home/sources/docs/delivery/records/r2-3-002.md",
            "/agent/home/sources/docs/evaluation-scenarios/ontology-modeling-team-l3/tester-only/answer-contract.json",
            "/agent/home/tester-only",
            "/agent/home/history",
            "/agent/home/secrets",
        )
        formal_acceptance_run = self._is_formal_acceptance_run(run)
        for agent in self.agents.values():
            sibling_process_paths = []
            for candidate in self.agents.values():
                if candidate.agent_id == agent.agent_id:
                    continue
                pid = candidate.app_server_host_pid
                if not isinstance(pid, int) or pid <= 0:
                    raise CodexRuntimeError("sibling app-server host PID is unavailable for visibility probe")
                sibling_process_paths.append(f"/proc/{pid}/environ")
            formal_acceptance_without_sources = (
                formal_acceptance_run and agent.package.role == "acceptance"
            )
            allowed = [] if formal_acceptance_without_sources else [
                "/agent/home/sources/" + source.relative_path.as_posix()
                for source in run.configuration.task.role_sources
                if agent.package.role in source.roles
            ]
            checks = " ".join(shlex.quote(path) for path in allowed)
            allowed_check = (
                f"for path in {checks}; do test -r \"$path\"; done"
                if checks
                else ":"
            )
            source_tree_check = (
                'test -z "$(find /agent/home/sources -type f -print -quit)"; '
                if formal_acceptance_without_sources
                else ""
            )
            sibling_socket = next(
                f"/agent/transport/{candidate.agent_id}.sock"
                for candidate in self.agents.values()
                if candidate.agent_id != agent.agent_id
            )
            denied = " ".join(
                shlex.quote(path)
                for path in (*forbidden_common, sibling_socket, *sibling_process_paths)
            )
            script = (
                "set -eu; "
                "test -e /proc/self/environ; "
                f"{source_tree_check}"
                f"{allowed_check}; "
                f"for path in {denied}; do test ! -e \"$path\"; done"
            )
            command = self.namespace_command(agent)
            separator = command.index("--")
            probe_command = command[: separator + 1] + ["/bin/sh", "-c", script]
            descriptors = agent.retrieval_asset_fds
            try:
                completed = subprocess.run(
                    probe_command,
                    text=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    pass_fds=descriptors,
                )
            finally:
                self._close_retrieval_asset_fds(agent)
            if completed.returncode != 0:
                raise CodexRuntimeError(f"role Runtime visibility probe failed for {agent.agent_id}")
            result[agent.agent_id] = {
                "allowed_path_count": len(allowed),
                "forbidden_path_categories": ["repo", "sibling", "socket", "tester", "history", "sibling-process", "secret"],
            }
        return result

    def _stage_skills(self, agent: _Agent) -> None:
        seen: set[str] = set()
        for source in agent.package.required_skills:
            skill_dir = source.parent
            target = agent.skills / skill_dir.name
            if target.name in seen:
                raise CodexRuntimeError("duplicate staged Skill directory")
            seen.add(target.name)
            shutil.copytree(skill_dir, target, symlinks=False)
            for item in target.rglob("*"):
                if item.is_symlink():
                    raise CodexRuntimeError("Skill staging refuses symlinks")
                if item.is_file():
                    os.chmod(item, 0o444)

    def _write_config(self, run: Any, agent: _Agent) -> None:
        task = getattr(getattr(run, "configuration", None), "task", None)
        formal = self._is_formal_acceptance_run(run)
        deepseek_enabled = bool(
            not formal
            and getattr(self, "_deepseek_enabled", False)
        )
        model_override = self._validated_model_override(agent.package, formal=formal)
        capability_operations = self._role_capability_operations(agent.package.role, run=run)
        formal_capability = bool(capability_operations)
        formal_acceptance_auth = (
            self._is_formal_acceptance_run(run) and agent.package.role == "acceptance"
        )
        if agent.package.role == "protocol" and getattr(task, "schema_version", 1) == 2:
            run_id = getattr(run, "run_id", None)
            if not isinstance(run_id, str) or not run_id:
                raise CodexRuntimeError(
                    "v2 Protocol mechanics MCP requires a run ID runtime binding"
                )
            if self._run_id is not None and self._run_id != run_id:
                raise CodexRuntimeError(
                    "v2 Protocol mechanics MCP run ID drifts from the active runtime"
                )
        # Only the Protocol receives its platform key/config.  Formal roles on
        # external credential routes use the shared loopback provider sessions
        # and therefore never receive auth.json; formal ``openai-codex`` roles
        # receive the Host ChatGPT login cache staged into their own isolated
        # CODEX_HOME, unlinked by the first-turn auth barrier before any
        # model-selected dispatch; historical/non-formal roles retain private
        # auth staging.  auth.json is never projected to a deepseek-direct role.
        if formal:
            binding_provider_id = (
                model_override.provider_id
                if isinstance(model_override, RoleModelBinding)
                else None
            )
            if uses_external_credential_session(binding_provider_id or ""):
                if self._provider_sessions is None:
                    raise CodexRuntimeError("formal provider sessions are unavailable")
                agent.auth_path = None
                agent.credential_mode = "provider_proxy"
                agent.auth_barrier_pending = True
            else:
                host_auth = self.preflight_host_auth()
                self._remember_secret(self._read_secret_bytes(host_auth))
                auth_path = agent.home / "auth.json"
                self._stage_private_auth(host_auth, auth_path)
                agent.auth_path = auth_path
                agent.credential_mode = "file_auth"
                agent.auth_barrier_pending = True
        elif agent.package.role != "acceptance":
            host_auth = self.preflight_host_auth()
            self._remember_secret(self._read_secret_bytes(host_auth))
            auth_path = agent.home / "auth.json"
            self._stage_private_auth(host_auth, auth_path)
            agent.auth_path = auth_path
            agent.credential_mode = "file_auth"
            agent.auth_barrier_pending = False
        elif formal_acceptance_auth:
            host_auth = self.preflight_host_auth()
            self._remember_secret(self._read_secret_bytes(host_auth))
            auth_path = agent.home / "auth.json"
            self._stage_private_auth(host_auth, auth_path)
            agent.auth_path = auth_path
            agent.auth_barrier_pending = True
        shutil.copyfile(
            self.root / "modeling_team" / "transport_mcp.py",
            agent.home / "transport_mcp.py",
        )
        # The transport is launched as an isolated standalone script.  Stage
        # its one local import beside it instead of relying on the checkout or
        # an inherited PYTHONPATH, which the private Runtime namespace must not
        # expose.
        shutil.copyfile(
            self.root / "modeling_team" / "interventions.py",
            agent.home / "interventions.py",
        )
        source_root = run.root / "sources"
        if getattr(task, "schema_version", 1) == 2:
            source_root = source_root / agent.package.role
        if agent.package.role == "acceptance":
            # Keep the mount point for the Runtime namespace, but never stage
            # approved source bytes or source-manifest paths into Acceptance.
            (agent.home / "sources").mkdir(mode=0o700)
        else:
            shutil.copytree(source_root, agent.home / "sources")
        os.chmod(agent.home / "transport_mcp.py", 0o444)
        os.chmod(agent.home / "interventions.py", 0o444)
        # This private config deliberately does not inherit the user's Codex config.  The
        # CLI flags below are a second, command-line enforced layer because several of
        # these are stable features enabled by default in interactive Codex installations.
        # A Team Profile owns the only model-visible tool surface for this experiment.
        lines = [
            'sandbox_mode = "read-only"',
            'web_search = "disabled"',
            "[features]",
            "apps = false",
            "plugins = false",
            "multi_agent = false",
            "multi_agent_v2 = false",
            "browser_use = false",
            "computer_use = false",
            "image_generation = false",
            "memories = false",
            "hooks = false",
            "skill_search = false",
            "tool_suggest = false",
            "[mcp_servers.team_transport]",
            'command = "/usr/bin/python3"',
            'args = ["/agent/home/transport_mcp.py"]',
            "required = true",
            "[mcp_servers.team_transport.env]",
            f'TEAM_TRANSPORT_SOCKET = "/agent/transport/{agent.agent_id}.sock"',
        ]
        modeling_read_proxy = (
            getattr(run, "modeling_read_proxy", None)
            if agent.package.role == "modeling" and self._is_r23003_run(run)
            else None
        )
        if agent.package.role == "modeling" and self._is_r23003_run(run):
            if modeling_read_proxy is None or not getattr(modeling_read_proxy, "active", False):
                raise CodexRuntimeError("R2.3-003 Modeling read proxy is unavailable")
            proxy_token_path = agent.home / "modeling-read-proxy.token"
            self._remember_secret(modeling_read_proxy.token.encode("utf-8"))
            self._write_child_private(
                proxy_token_path, modeling_read_proxy.token.encode("utf-8"), 0o400
            )
            shutil.copyfile(
                self.root / "modeling_team" / "read_proxy_mcp.py",
                agent.home / "read_proxy_mcp.py",
            )
            os.chmod(agent.home / "read_proxy_mcp.py", 0o444)
            lines.extend(
                [
                    "[mcp_servers.modeling_read_proxy]",
                    'command = "/usr/bin/python3"',
                    'args = ["/agent/home/read_proxy_mcp.py", "--stdio", "--socket", "/agent/home/modeling-read-proxy.sock", "--token-file", "/agent/home/modeling-read-proxy.token"]',
                    'default_tools_approval_mode = "approve"',
                    "required = true",
                    "[mcp_servers.modeling_read_proxy.env]",
                    'PLATFORM_PROXY_MODE = "modeling"',
                    f'PLATFORM_PROXY_PROJECT_ID = {json.dumps(str(run.scope["project_id"]))}',
                    f'PLATFORM_PROXY_ONTOLOGY_ID = {json.dumps(str(run.scope["ontology_id"]))}',
                ]
            )
        if agent.package.role == "protocol":
            key = run.protocol_key
            if not key:
                raise CodexRuntimeError(
                    "Protocol key is required before Runtime startup"
                )
            self._remember_secret(key)
            platform = agent.home / "platform"
            shutil.copytree(self.root / "backend" / "app", platform / "app")
            # R3.0-002: the same unified predicate covers formal acceptance
            # runs and multi_slice_workflow tasks (see the predicate docstring).
            platform_gate_enabled = self._candidate_platform_gate_enabled_for_run(run)
            if platform_gate_enabled:
                CandidatePlatformGate.ensure(run.root / "candidate-gate")
            lines.extend(
                protocol_mcp_launch_spec(
                    agent.platform_tools,
                    schema_version=getattr(task, "schema_version", 1),
                    candidate_gate_path=(
                        CANDIDATE_PLATFORM_GATE_MOUNT if platform_gate_enabled else None
                    ),
                ).config_lines(api_key=key)
            )
            if getattr(task, "schema_version", 1) == 2:
                lines.extend(
                    [
                        "[mcp_servers.protocol_mechanics]",
                        'command = "/usr/bin/python3"',
                        'args = ["/opt/protocol-retrieval-mcp.py"]',
                        "required = true",
                        "[mcp_servers.protocol_mechanics.env]",
                        f'PROTOCOL_RUNTIME_RUN_ID = {json.dumps(run_id)}',
                        f'PROTOCOL_PROOF_GATE = {json.dumps("1" if agent.proof_gate else "0")}',
                        f'PROTOCOL_FORMAL_CANDIDATE_GATE = {json.dumps("1" if self._coordination_enabled else "0")}',
                    ]
                )
        if formal_capability:
            capability_script = agent.home / "runner_capability_mcp.py"
            shutil.copyfile(self.root / "modeling_team" / "capability_mcp.py", capability_script)
            os.chmod(capability_script, 0o444)
            token_source = self._acceptance.capability_token_path(agent.package.role)
            token_target = agent.home / "runner-capability.token"
            capability_token = token_source.read_text(encoding="utf-8")
            self._remember_secret(capability_token)
            token_target.write_text(capability_token, encoding="utf-8")
            os.chmod(token_target, 0o400)
            lines.extend(
                [
                    "[mcp_servers.runner_capability]",
                    'command = "/usr/bin/python3"',
                    'args = ["/agent/home/runner_capability_mcp.py", "--stdio", "--socket", "/agent/home/runner-capability.sock", "--token-file", "/agent/home/runner-capability.token"]',
                    "required = true",
                ]
            )
        if isinstance(model_override, RoleModelBinding):
            binding = model_override
            if formal and not uses_external_credential_session(binding.provider_id):
                # ``openai-codex`` projects onto Codex's built-in provider with
                # no custom provider table and no base URL.  ``lines`` starts
                # with the scalar sandbox/web_search settings and the
                # ``[features]`` table header here (no model trio has been
                # prepended yet), so splice around the full list: dropping the
                # first entries would leave the feature flags as bare top-level
                # keys, which Codex 0.147.0 parses as typed tables and rejects
                # on the ``skills/list`` config reload.
                provider_lines = _formal_codex_builtin_config_lines(binding)
                lines = provider_lines[:3] + lines + provider_lines[3:]
                self._seed_models_cache(agent.home, binding.model)
            else:
                lines = [
                    f'model = "{binding.model}"',
                    f'model_provider = "{binding.provider_id}"',
                    f'model_reasoning_effort = "{binding.effective_effort}"',
                    *lines,
                ]
                if formal:
                    sessions = self._provider_sessions
                    if sessions is None:
                        raise CodexRuntimeError("formal provider sessions are unavailable")
                    provider_lines = _formal_provider_config_lines(
                        binding, sessions.base_url_for(binding.provider_id)
                    )
                    # ``lines`` already carries the package model trio above.  Keep one
                    # authoritative trio and append only the provider/shell tables;
                    # repeating the scalar keys makes the real app-server reject the
                    # config before initialize with a TOML duplicate-key error.
                    lines = provider_lines[:3] + lines[3:] + provider_lines[3:]
        elif model_override is not None:
            model, provider, reasoning = model_override
            lines = [
                f'model = "{model}"',
                f'model_provider = "{provider}"',
                f'model_reasoning_effort = "{reasoning}"',
                *lines,
            ]
        elif deepseek_enabled:
            provider_lines = _deepseek_provider_config_lines()
            # Keep scalar settings before the first TOML table; append provider and
            # shell-policy tables after the existing MCP tables.
            lines = provider_lines[:3] + lines + provider_lines[3:]
        capability_names = (
            list(capability_operations)
            if formal_capability
            else (
                # R3.0-008B conservation: the non-staged manifest keeps the
                # pre-008B role registry view (the staged operation never
                # appears in a non-staged capability manifest).
                [
                    operation
                    for operation in ROLE_OPERATIONS.get(agent.package.role, ())
                    if operation != STAGED_PROTOCOL_OPERATION
                ]
                if agent.package.role != "modeling"
                else []
            )
        )
        capability_manifest = agent.home / "runner-capabilities.json"
        carrier = getattr(run, "acceptance", None)
        capability_descriptors = None
        if (
            formal_capability
            and carrier is not None
            and hasattr(carrier, "capability_descriptors")
        ):
            descriptors = carrier.capability_descriptors
            if isinstance(descriptors, dict) and agent.package.role in descriptors:
                capability_descriptors = {agent.package.role: descriptors[agent.package.role]}
        capability_manifest.write_text(
            json.dumps(
                {
                    "agent_id": agent.agent_id,
                    "role": agent.package.role,
                    "capabilities": capability_names,
                    "team_transport_terminal_state": False,
                    "opaque_handles_only": agent.package.role == "acceptance",
                    **({"capability_descriptors": capability_descriptors} if capability_descriptors else {}),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        os.chmod(capability_manifest, 0o400)
        (agent.home / "config.toml").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
        os.chmod(agent.home / "config.toml", 0o600)

    def _seed_models_cache(self, home: Path, model: str) -> None:
        """Seed Codex's per-home models cache for the built-in provider route.

        Codex 0.147.0 resolves ``thread/start`` through the models manager: with
        no usable ``models_cache.json`` entry it runs an online refresh
        (``GET chatgpt.com/backend-api/codex/models``) whose slow-path abort
        (``timeout waiting for child process to exit``) races between a
        tolerated fallback and a fatal JSON-RPC ``-32603`` (R2.3-008 start3,
        third started role).  A version-matched, fresh cache entry makes the
        ``online_if_uncached`` strategy hit the cache and skips the refresh
        entirely, so startup is deterministic.  Applies to both persistent
        roles and fresh Examiner children (which run the same ``thread/start``
        after ``semantic_start``).  The snapshot is the official endpoint's
        model metadata (secret-free); Codex itself rejects a client version
        mismatch and falls back to its own refresh, and an unknown model slug
        keeps the legacy unseeded behavior.
        """

        snapshot_path = (
            self.root / "modeling_team" / "references" / "codex-models-cache-0.147.0.json"
        )
        try:
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        models = snapshot.get("models") if isinstance(snapshot, dict) else None
        slugs = (
            {
                entry.get("slug")
                for entry in models
                if isinstance(entry, dict) and isinstance(entry.get("slug"), str)
            }
            if isinstance(models, list)
            else set()
        )
        if model not in slugs:
            return
        seeded = dict(snapshot)
        seeded["fetched_at"] = (
            datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
        )
        cache_path = home / "models_cache.json"
        cache_path.write_text(json.dumps(seeded), encoding="utf-8")
        os.chmod(cache_path, 0o600)

    def _protocol_interpreter_mounts(self) -> list[str]:
        """Bind the venv interpreter plus every absolute symlink target's prefix.

        ``backend/.venv/bin/python`` is a uv-managed *absolute* symlink into the
        uv Python store (R2.3-008 start4).  ``--ro-bind`` of ``/backend/.venv``
        preserves that symlink verbatim, so unless the target's interpreter
        runtime prefix also exists at its own path inside the namespace the
        Protocol ``ontology_platform`` MCP spawn dies with ``No such file or
        directory (os error 2)``.  Walk the interpreter's symlink chain and
        bind each absolute target's runtime prefix (the target lives in
        ``<prefix>/bin``, and CPython resolves its standard library relative to
        that prefix); relative targets resolve inside the already-bound venv
        and need no extra mount.  The fully resolved interpreter runtime stays
        bound for ``pyvenv.cfg``/sysconfig lookups.
        """

        venv = self.root / "backend" / ".venv"
        resolved_venv = venv.resolve()
        resolved_python = (venv / "bin" / "python").resolve()
        runtime_root = resolved_python.parent.parent
        directories = [runtime_root]
        bound: set[Path] = {runtime_root}
        link: Path | None = venv / "bin" / "python"
        visited: set[Path] = set()
        while link is not None and link not in visited and len(visited) < 8:
            visited.add(link)
            if not link.is_symlink():
                break
            target = Path(os.readlink(link))
            if target.is_absolute():
                candidate = target
            else:
                candidate = link.parent / target
            directory = candidate.parent.parent
            inside_venv = directory == resolved_venv or resolved_venv in directory.parents
            if not inside_venv and directory not in bound:
                bound.add(directory)
                directories.append(directory)
            link = candidate
        mounts = [
            "--dir",
            "/backend",
            "--ro-bind",
            str(self.root / "backend" / "app"),
            "/backend/app",
            "--ro-bind",
            str(venv),
            "/backend/.venv",
        ]
        # Every ancestor must exist as a mount point before any subtree bind is
        # applied, and base ro-binds (/usr, /lib, ...) already provide theirs.
        preexisting = ("/usr", "/bin", "/lib", "/lib64", "/etc")
        created: set[str] = set()
        for directory in directories:
            ancestor = Path("/")
            for part in directory.parts[1:-1]:
                ancestor = ancestor / part
                if str(ancestor) in created or any(
                    ancestor.is_relative_to(base) for base in preexisting
                ):
                    continue
                created.add(str(ancestor))
                mounts.extend(["--dir", str(ancestor)])
        for directory in directories:
            mounts.extend(["--ro-bind", str(directory), str(directory)])
        return mounts

    def _thread_sandbox(self, agent: _Agent) -> str:
        """R3.0-006 start3: only the multi-slice Coordinator writes run-root
        artifacts; every other role/task keeps the frozen package sandbox
        byte-for-byte.

        R3.0-008B staged runs additionally elevate the modeling and protocol
        roles: each owns writable staged artifact directories (design §3.9
        bind table) inside the otherwise read-only package sandbox.
        """

        if agent.package.role == "coordinator" and getattr(
            self, "_multi_slice_scenario_map_enabled", False
        ):
            return "workspace-write"
        if agent.package.role in {"modeling", "protocol"} and getattr(
            self, "_staged_decisions_enabled", False
        ):
            return "workspace-write"
        return agent.package.runtime["codex"]["sandbox"]

    def _coordinator_scenario_map_bind(self, agent: _Agent) -> list[str]:
        """R3.0-006 start3: writable bind of the run-root ``scenario-map/``
        directory into the Coordinator namespace.

        The frozen Coordinator instructions maintain the six-section map,
        topology decision, and protection-IRI suggestions at cwd-relative
        ``scenario-map/...`` paths; without this bind (and the matching
        workspace-write thread sandbox) every creation attempt is rejected by
        the read-only package sandbox and the topology gate can never open.
        Multi-slice runs only; every other task keeps the byte-identical
        namespace command.
        """

        if agent.package.role != "coordinator" or not getattr(
            self, "_multi_slice_scenario_map_enabled", False
        ):
            return []
        if self._run_root is None:
            raise CodexRuntimeError(
                "multi-slice Coordinator scenario-map mount is missing its run root"
            )
        scenario_map_directory = self._run_root / "scenario-map"
        if not scenario_map_directory.is_dir():
            raise CodexRuntimeError(
                "multi-slice Coordinator scenario-map directory was not prepared"
            )
        return [
            "--bind",
            str(scenario_map_directory),
            "/agent/work/scenario-map",
        ]

    def _staged_decision_binds(self, agent: _Agent) -> list[str]:
        """R3.0-008B staged-decision directory binds (design §3.9 item 5).

        Bind units are directories, prepared (mkdir-only) by TeamRunner before
        the roster starts; no staged file is ever pre-created because an absent
        file IS the gate semantics.  All three roles see the ``value-semantics/``
        tree read-only; each role additionally receives writable binds for
        exactly the directories it uniquely owns.  ``submission-receipts/``
        and ``submission-intents/`` are Runner-host-owned and never bound.
        Non-staged runs return an empty list (byte-identical command, F1).

        R3.0-009 unified runs (2026-09-09 execution-gap closure G2) split the
        ``stage3-neutral-graph`` tree so that the neutral candidate slot stays
        published by Modeling while the materialization plans are published by
        Protocol alone, using the same sequential-overlay mechanism as the
        value-semantics tree: bwrap applies arguments in order, so a later
        bind of a subdirectory overrides the enclosing bind.  Modeling keeps
        the writable parent (slot root file and ``candidates/``) with a
        read-only overlay on ``materialization-plans/``; Protocol gets the
        read-only parent plus a writable overlay on ``materialization-plans/``;
        the Coordinator sees the whole tree read-only; the competency-question
        and every other role receive no stage3 mount at all.  Non-unified
        staged runs keep the previous mount sequence byte-for-byte.
        """

        if not getattr(self, "_staged_decisions_enabled", False):
            return []
        if self._run_root is None:
            raise CodexRuntimeError("staged decision mounts are missing their run root")
        role = agent.package.role
        read_only: list[str] = ["--ro-bind"]
        value_semantics = self._run_root / "value-semantics"
        if not value_semantics.is_dir():
            raise CodexRuntimeError("staged value-semantics directory was not prepared")
        unified = bool(getattr(self, "_unified_graph", False))
        writable_by_role: dict[str, tuple[str, ...]] = {
            "modeling": (
                "value-semantics/conclusions",
                "value-semantics/conclusions-archive",
                "stage3-neutral-graph",
            ),
            "coordinator": (
                "value-semantics/unlock",
                "value-semantics/approvals",
                "joint-acceptance",
            ),
            "protocol": ("value-semantics/ledger",),
        }
        owned = writable_by_role.get(role, ())
        mounts: list[str] = list(read_only)
        mounts.extend([str(value_semantics), "/agent/work/value-semantics"])
        for relative in owned:
            directory = self._run_root / relative
            if not directory.is_dir():
                raise CodexRuntimeError(
                    f"staged writable directory was not prepared: {relative}"
                )
            # The later per-subdirectory --bind nests on top of the read-only
            # value-semantics bind (bwrap applies arguments sequentially).
            mounts.extend(["--bind", str(directory), f"/agent/work/{relative}"])
        if not unified:
            return mounts
        neutral_graph = self._run_root / "stage3-neutral-graph"
        plans = neutral_graph / "materialization-plans"
        if not neutral_graph.is_dir() or not plans.is_dir():
            raise CodexRuntimeError(
                "unified staged stage3 directories were not prepared"
            )
        if role == "modeling":
            # The writable parent above stays; the read-only overlay below it
            # makes materialization-plans immutable in this namespace.
            mounts.extend(
                [
                    "--ro-bind",
                    str(plans),
                    "/agent/work/stage3-neutral-graph/materialization-plans",
                ]
            )
        elif role == "protocol":
            mounts.extend(
                [
                    "--ro-bind",
                    str(neutral_graph),
                    "/agent/work/stage3-neutral-graph",
                    "--bind",
                    str(plans),
                    "/agent/work/stage3-neutral-graph/materialization-plans",
                ]
            )
        elif role == "coordinator":
            mounts.extend(
                [
                    "--ro-bind",
                    str(neutral_graph),
                    "/agent/work/stage3-neutral-graph",
                ]
            )
        return mounts

    def _competency_question_binds(self, agent: _Agent) -> list[str]:
        """R3.0-011 per-role read-only binds for the competency-question tree.

        Production roles only ever see the ``public/`` projection directory
        (the same per-role read-only directory bind pattern as the run-root
        scenario-map mount); the competency-question role additionally sees its
        own ``private/`` and ``reviews/`` records.  ``frozen/``,
        ``acceptance-v3/hidden-batch/`` and ``acceptance-v3/reports/`` stay
        host-only and are never bound into any Agent namespace (design §3.4).
        Non-011 runs return an empty list (byte-identical command).
        """

        if not self._competency_questions_enabled_for_active_run(None):
            return []
        if self._run_root is None:
            raise CodexRuntimeError("competency-question mounts are missing their run root")
        role = agent.package.role
        if role == COMPETENCY_QUESTION_ROLE:
            relatives = (
                "competency-questions/private",
                "competency-questions/reviews",
            )
        elif role in {"coordinator", "modeling", "protocol"}:
            relatives = ("competency-questions/public",)
        else:
            return []
        mounts: list[str] = []
        for relative in relatives:
            directory = self._run_root / relative
            if not directory.is_dir():
                raise CodexRuntimeError(
                    f"competency-question directory was not prepared: {relative}"
                )
            mounts.extend(["--ro-bind", str(directory), f"/agent/work/{relative}"])
        return mounts

    def namespace_command(self, agent: _Agent) -> list[str]:
        binary = shutil.which(self.codex_binary) or self.codex_binary
        if not self.use_bwrap:
            return [binary, "app-server"]
        bwrap = shutil.which("bwrap")
        if not bwrap:
            raise CodexRuntimeError("bubblewrap is required for per-Agent isolation")
        # No host root or repo mount: only immutable runtime libraries and this Agent's private inputs.
        command = [
            bwrap,
            "--die-with-parent",
            "--unshare-pid",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
        ]
        for source in (
            "/usr",
            "/bin",
            "/lib",
            "/lib64",
            "/etc/ld.so.cache",
            "/etc/resolv.conf",
            "/etc/hosts",
            "/etc/nsswitch.conf",
            "/etc/ssl/certs",
        ):
            if Path(source).exists():
                command.extend(["--ro-bind", source, source])
        command += [
            "--dir",
            "/agent",
            "--bind",
            str(agent.home),
            "/agent/home",
            "--bind",
            str(agent.work),
            "/agent/work",
            *self._coordinator_scenario_map_bind(agent),
            *self._staged_decision_binds(agent),
            *self._competency_question_binds(agent),
            "--ro-bind",
            str(agent.skills),
            "/skills",
            "--dir",
            "/agent/transport",
            "--bind",
            str(self._transport_root() / f"{agent.agent_id}.sock"),
            f"/agent/transport/{agent.agent_id}.sock",
            "--chdir",
            "/agent/work",
            "--setenv",
            "CODEX_HOME",
            "/agent/home",
            "--setenv",
            "TERM",
            "xterm-256color",
        ]
        if (
            # A non-empty operation set already implies formal coordination or
            # the R3.0-008B staged protocol capability, so the staged
            # non-formal protocol role also gets its capability socket bound.
            self._acceptance is not None
            and self._role_capability_operations(agent.package.role)
        ):
            command[command.index("--chdir") : command.index("--chdir")] = [
                "--bind",
                str(self._acceptance.capability_socket_path(agent.package.role)),
                "/agent/home/runner-capability.sock",
            ]
        if agent.package.role == "modeling" and self._is_r23003_run(self._active_run):
            proxy = getattr(self._active_run, "modeling_read_proxy", None)
            socket_path = getattr(proxy, "socket_path", None)
            if not isinstance(socket_path, Path) or not socket_path.exists():
                raise CodexRuntimeError("R2.3-003 Modeling read proxy socket is unavailable")
            command[command.index("--chdir") : command.index("--chdir")] = [
                "--bind",
                str(socket_path),
                "/agent/home/modeling-read-proxy.sock",
            ]
        app_server_command = [
            "--config",
            'web_search="disabled"',
            "--disable",
            "apps",
            "--disable",
            "plugins",
            "--disable",
            "multi_agent",
            "--disable",
            "multi_agent_v2",
            "--disable",
            "browser_use",
            "--disable",
            "computer_use",
            "--disable",
            "image_generation",
            "--disable",
            "memories",
            "--disable",
            "hooks",
            "app-server",
        ]
        if agent.package.role == "protocol":
            command[command.index("--chdir") : command.index("--chdir")] = (
                self._protocol_interpreter_mounts()
            )
            if agent.mechanics_contract_path is not None:
                self._read_protocol_mechanics_contract(agent)
                command[command.index("--chdir") : command.index("--chdir")] = [
                    "--dir",
                    "/opt",
                    "--ro-bind",
                    str(agent.mechanics_contract_path),
                    "/opt/mechanics-contract.json",
                ]
            if (
                agent.retrieval_mcp_path is not None
                or agent.retrieval_verifier_path is not None
                or agent.proof_v2_path is not None
            ):
                descriptors = self._open_protocol_retrieval_assets(agent)
                mounts = [
                    "--dir",
                    "/opt",
                    "--ro-bind",
                    f"/proc/self/fd/{descriptors[0]}",
                    "/opt/protocol-retrieval-mcp.py",
                    "--ro-bind",
                    f"/proc/self/fd/{descriptors[1]}",
                    "/opt/protocol_mechanics.py",
                ]
                if len(descriptors) == 3:
                    mounts.extend(
                        [
                            "--ro-bind",
                            f"/proc/self/fd/{descriptors[2]}",
                            "/opt/proof_v2.py",
                        ]
                    )
                command[command.index("--chdir") : command.index("--chdir")] = mounts
            if agent.schema_version == 2:
                if self._candidate_platform_gate_enabled:
                    if self._run_root is None:
                        raise CodexRuntimeError("Protocol candidate gate is missing its run root")
                    gate_directory = self._run_root / "candidate-gate"
                    CandidatePlatformGate.ensure(gate_directory)
                    command[command.index("--chdir") : command.index("--chdir")] = [
                        "--dir",
                        CANDIDATE_PLATFORM_GATE_DIR_MOUNT,
                        "--ro-bind",
                        str(gate_directory),
                        CANDIDATE_PLATFORM_GATE_DIR_MOUNT,
                    ]
                reasoner = self._protocol_reasoner_script()
                command[command.index("--chdir") : command.index("--chdir")] = [
                    "--dir",
                    "/backend/scripts",
                    "--ro-bind",
                    str(reasoner),
                    "/backend/scripts/dev_owl_reasoner.py",
                ]
        companion_mounts: list[str] = []
        # R2.3-008 start6: Codex 0.147.0 resolves its tool-execution companion
        # relative to the mounted binary's directory; without the bind every
        # tool call inside the namespace fails with ENOENT.  Additive only.
        companion = self._codex_companion_binary()
        if companion is not None:
            companion_mounts = [
                "--ro-bind",
                str(companion),
                "/agent/bin/codex-code-mode-host",
            ]
        command[command.index("--chdir") : command.index("--chdir")] = [
            "--dir",
            "/agent/bin",
            "--ro-bind",
            binary,
            "/agent/bin/codex",
            *companion_mounts,
        ]
        return command + ["--", "/agent/bin/codex", *app_server_command]

    def _protocol_reasoner_script(self) -> Path:
        script = self.root / "backend" / "scripts" / "dev_owl_reasoner.py"
        try:
            metadata = os.lstat(script)
        except OSError as exc:
            raise CodexRuntimeError("Protocol reasoner script is unavailable") from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise CodexRuntimeError("Protocol reasoner script is unavailable")
        return script

    def _transport_root(self) -> Path:
        if self._run_root is None:
            raise CodexRuntimeError("Runtime is missing its run root")
        state_file = self._run_root / "transport-root"
        if state_file.is_file():
            return Path(state_file.read_text(encoding="utf-8"))
        return self._run_root / "transport" / "broker"

    def _start_process(self, agent: _Agent) -> subprocess.Popen[str]:
        formal = self._coordination_enabled
        model_override = self._validated_model_override(agent.package, formal=formal)
        api_key = (
            self._resolve_deepseek_api_key()
            if (not formal and getattr(self, "_deepseek_enabled", False))
            and model_override is None
            else None
        )
        command = self.namespace_command(agent)
        descriptors = agent.retrieval_asset_fds
        try:
            process = self.process_factory(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                start_new_session=True,
                pass_fds=descriptors,
                env=_minimal_codex_process_env(agent.home, api_key),
            )
            agent.process = process
            if formal:
                self._start_stderr_drain(agent)
            return process
        finally:
            self._close_retrieval_asset_fds(agent)

    def _open_protocol_retrieval_assets(self, agent: _Agent) -> tuple[int, ...]:
        """Open immutable wrapper/verifier/proof descriptors for the Protocol-only bwrap mount."""
        if agent.retrieval_asset_fds:
            expected_count = 3 if agent.proof_gate else 2
            if len(agent.retrieval_asset_fds) != expected_count:
                raise CodexRuntimeError("Protocol retrieval MCP descriptor state is invalid")
            return agent.retrieval_asset_fds
        if (
            self._run_root is None
            or agent.package.role != "protocol"
            or agent.schema_version != 2
            or self.agents.get(agent.agent_id) is not agent
        ):
            raise CodexRuntimeError("Protocol retrieval MCP Agent identity is invalid")
        expected_root = self._run_root / "runtime-assets" / "protocol"
        expected = [
            (agent.retrieval_mcp_path, expected_root / "protocol-retrieval-mcp.py", self.root / "modeling_team/protocol_retrieval_mcp.py", 0o444),
            (agent.retrieval_verifier_path, expected_root / "protocol_mechanics.py", self.root / "modeling_team/protocol_mechanics.py", 0o444),
        ]
        if agent.proof_gate:
            expected.append(
                (agent.proof_v2_path, expected_root / "proof_v2.py", self.root / "modeling_team/proof_v2.py", 0o600)
            )
        descriptors: list[int] = []
        try:
            for path, expected_path, source, mode in expected:
                if path != expected_path:
                    raise CodexRuntimeError("Protocol retrieval MCP asset path is invalid")
                parent = os.lstat(expected_path.parent)
                if (
                    stat.S_ISLNK(parent.st_mode)
                    or not stat.S_ISDIR(parent.st_mode)
                    or stat.S_IMODE(parent.st_mode) != 0o700
                    or parent.st_uid != os.getuid()
                ):
                    raise CodexRuntimeError("Protocol retrieval MCP asset parent is invalid")
                try:
                    descriptor = os.open(expected_path, os.O_RDONLY | os.O_NOFOLLOW)
                except OSError as exc:
                    raise CodexRuntimeError("Protocol retrieval MCP asset is unavailable") from exc
                metadata = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or stat.S_IMODE(metadata.st_mode) != mode
                    or metadata.st_uid != os.getuid()
                ):
                    os.close(descriptor)
                    raise CodexRuntimeError("Protocol retrieval MCP asset metadata is invalid")
                payload = bytearray()
                while chunk := os.read(descriptor, 65536):
                    payload.extend(chunk)
                if hashlib.sha256(payload).hexdigest() != digest_file(source):
                    os.close(descriptor)
                    raise CodexRuntimeError("Protocol retrieval MCP asset digest is invalid")
                descriptors.append(descriptor)
            agent.retrieval_asset_fds = tuple(descriptors)
            return tuple(descriptors)
        except Exception:
            for descriptor in descriptors:
                os.close(descriptor)
            raise

    @staticmethod
    def _close_retrieval_asset_fds(agent: _Agent) -> None:
        for descriptor in agent.retrieval_asset_fds:
            try:
                os.close(descriptor)
            except OSError:
                pass
        agent.retrieval_asset_fds = ()

    @staticmethod
    def _host_child_pids(pid: int) -> list[int]:
        children = Path(f"/proc/{pid}/task/{pid}/children")
        try:
            return [int(value) for value in children.read_text(encoding="utf-8").split()]
        except (OSError, ValueError) as exc:
            raise CodexRuntimeError("cannot inspect app-server process tree") from exc

    @staticmethod
    def _host_process_identity(pid: int) -> tuple[str, str]:
        try:
            command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(
                "utf-8", errors="replace"
            )
            name = Path(f"/proc/{pid}/comm").read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise CodexRuntimeError("cannot inspect app-server process identity") from exc
        return name, command

    def _app_server_host_pid(self, agent: _Agent) -> int:
        """Resolve the inner app-server PID, never retaining wrapper PIDs as evidence."""
        wrapper_pid = getattr(agent.process, "pid", None)
        if not isinstance(wrapper_pid, int) or wrapper_pid <= 0:
            raise CodexRuntimeError("app-server wrapper host PID is unavailable")
        pending = [wrapper_pid]
        leaves: list[int] = []
        seen: set[int] = set()
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            children = self._host_child_pids(current)
            if children:
                pending.extend(children)
            else:
                leaves.append(current)
        identities = {
            pid: self._host_process_identity(pid) for pid in seen - {wrapper_pid}
        }
        candidates = [
            pid for pid, (name, command) in identities.items() if name != "bwrap" and "app-server" in command
        ]
        if len(candidates) == 1:
            return candidates[0]
        if len(leaves) != 1 or leaves[0] == wrapper_pid:
            raise CodexRuntimeError("cannot resolve a unique app-server host PID")
        return leaves[0]

    def _rpc(
        self, agent: _Agent, method: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        with agent.io_lock:
            return self._rpc_locked(agent, method, params)

    @staticmethod
    def _turn_digest(turn_id: str | None) -> str | None:
        if not isinstance(turn_id, str) or not turn_id:
            return None
        return hashlib.sha256(turn_id.encode("utf-8")).hexdigest()

    @staticmethod
    def _validated_turn_id(value: object) -> str | None:
        return value if isinstance(value, str) and _SAFE_TURN_ID_RE.fullmatch(value) else None

    @classmethod
    def _provider_error_info(cls, value: object) -> tuple[str, int | None] | None:
        """Validate generated ``CodexErrorInfo`` and return a normalized variant."""

        if value is None:
            return "none", None
        if isinstance(value, str):
            return (value, None) if value in _PROVIDER_ERROR_VARIANTS else None
        if not isinstance(value, dict) or len(value) != 1:
            return None
        variant, payload = next(iter(value.items()))
        if variant not in _PROVIDER_ERROR_VARIANTS or not isinstance(payload, dict):
            return None
        if variant in _PROVIDER_HTTP_VARIANTS:
            if any(key != "httpStatusCode" for key in payload):
                return None
            status = payload.get("httpStatusCode")
            if status is not None and (
                not isinstance(status, int)
                or isinstance(status, bool)
                or not 0 <= status <= 65535
            ):
                return None
            return variant, status
        if variant == "activeTurnNotSteerable":
            if set(payload) != {"turnKind"} or payload.get("turnKind") not in {"review", "compact"}:
                return None
            return variant, None
        return None

    def _provider_error_detail(
        self, agent: _Agent, value: dict[str, Any]
    ) -> tuple[bool, dict[str, Any]]:
        """Strictly validate one ErrorNotification without retaining provider text."""

        params = value.get("params")
        malformed: dict[str, Any] = {
            "source": "provider-error",
            "reason": "provider-error-malformed",
            "variant": "malformed",
        }
        if not isinstance(params, dict) or set(params) != {"error", "willRetry", "threadId", "turnId"}:
            return False, malformed
        thread_id = params.get("threadId")
        turn_id = params.get("turnId")
        if not isinstance(thread_id, str) or not thread_id or not isinstance(turn_id, str) or not turn_id:
            return False, malformed
        expected_thread = agent.thread_id
        expected_turn = agent.active_turn_id or agent.last_started_turn_id
        if expected_thread is None or thread_id != expected_thread:
            malformed["variant"] = "thread-mismatch"
            return False, malformed
        if expected_turn is None or turn_id != expected_turn:
            malformed["variant"] = "turn-mismatch"
            malformed["turn_digest"] = self._turn_digest(turn_id)
            return False, malformed
        will_retry = params.get("willRetry")
        error = params.get("error")
        if not isinstance(will_retry, bool) or not isinstance(error, dict):
            return False, malformed
        if any(key not in {"message", "codexErrorInfo", "additionalDetails"} for key in error):
            return False, malformed
        if not isinstance(error.get("message"), str):
            return False, malformed
        if "additionalDetails" in error and error.get("additionalDetails") is not None and not isinstance(error.get("additionalDetails"), str):
            return False, malformed
        info = self._provider_error_info(error.get("codexErrorInfo"))
        if info is None:
            return False, malformed
        variant, status = info
        detail: dict[str, Any] = {
            "source": "provider-error",
            "reason": "provider-error-terminal" if not will_retry else "provider-error",
            "will_retry": will_retry,
            "variant": variant,
            "turn_digest": self._turn_digest(turn_id),
        }
        if status is not None:
            detail["http_status"] = status
        return True, detail

    def _handle_provider_error_notification(self, agent: _Agent, value: dict[str, Any]) -> None:
        valid, detail = self._provider_error_detail(agent, value)
        if not valid:
            self._latch_runtime_failure(agent, detail)
            return
        # A retryable provider error is observable but deliberately does not
        # refresh the inactivity clock; only allowlisted work notifications do.
        self._append_runtime_evidence("provider-error", detail)
        if detail.get("will_retry") is False:
            self._latch_runtime_failure(agent, detail)

    @staticmethod
    def _classify_steer_message(message: object) -> tuple[str, str | None]:
        if not isinstance(message, str):
            return "rpc_error", None
        normalized = message.strip()
        legacy_prefix = "app-server turn/steer failed: "
        if normalized.startswith(legacy_prefix):
            normalized = normalized[len(legacy_prefix) :]
        if normalized.casefold() == "no active turn to steer":
            return "no_active_turn_to_steer", None
        # The exact active-turn mismatch wording is the only provider text
        # interpreted.  The captured ID is validated and retained in memory only.
        match = re.fullmatch(
            r"(?:app-server turn/steer failed: )?expected active turn id `([^`]+)` but found `([^`]+)`",
            normalized,
        )
        if match:
            active = CodexRuntimeAdapter._validated_turn_id(match.group(2))
            if active is not None:
                return "active_turn_mismatch", active
        return "rpc_error", None

    @classmethod
    def _rpc_error_from_value(cls, method: str, value: object) -> CodexRuntimeRPCError:
        if not isinstance(value, dict):
            return CodexRuntimeRPCError(method, None, "malformed_rpc_error")
        code = value.get("code")
        if (
            not isinstance(code, int)
            or isinstance(code, bool)
            or not -(2**63) <= code <= (2**63 - 1)
            or not isinstance(value.get("message"), str)
        ):
            return CodexRuntimeRPCError(method, None, "malformed_rpc_error")
        message = value.get("message")
        category, active = cls._classify_steer_message(message) if method == "turn/steer" else ("rpc_error", None)
        return CodexRuntimeRPCError(
            method, code, category, active_turn_id=active, server_message=_sanitize_rpc_message(message)
        )

    @staticmethod
    def _is_progress_notification(value: Mapping[str, Any]) -> bool:
        method = value.get("method")
        if not isinstance(method, str):
            return False
        if "id" in value:
            return method in _PROGRESS_SERVER_REQUEST_METHODS
        return method in _PROGRESS_NOTIFICATION_METHODS

    def _rpc_locked(
        self, agent: _Agent, method: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        if (
            agent.process is None
            or agent.process.stdin is None
            or agent.process.stdout is None
        ):
            raise CodexRuntimeError("app-server is unavailable")
        if method == "turn/start" and agent.auth_barrier_pending:
            return self._first_turn_rpc_locked(agent, method, params)
        agent.request_id += 1
        request_id = agent.request_id
        agent.process.stdin.write(
            json.dumps(
                {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
            )
            + "\n"
        )
        agent.process.stdin.flush()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            line = self._read_output_line(agent, deadline - time.monotonic())
            if line is None:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CodexRuntimeError("malformed app-server JSON") from exc
            if not isinstance(value, dict):
                raise CodexRuntimeError("app-server message is not an object")
            if value.get("id") == request_id:
                if "error" in value:
                    raise self._rpc_error_from_value(method, value.get("error"))
                result = value.get("result", {})
                return result if isinstance(result, dict) else {}
            self._notification(agent, value)
            if getattr(agent, "runtime_failure", None) is not None:
                raise CodexRuntimeError("runtime failure is latched")
        raise CodexRuntimeError(f"app-server did not answer {method}")

    def _first_turn_rpc_locked(
        self, agent: _Agent, method: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Wait for the accepted first turn while guarding provider auth removal.

        Ordinary notifications are held until the matching response proves the turn
        identity.  A server request is never buffered: auth is unlinked first, then
        its typed fail-closed response is dispatched so a server waiting on that
        response cannot deadlock.  Every item is consumed exactly once by this loop.
        """

        if agent.process is None or agent.process.stdin is None:
            raise CodexRuntimeError("app-server is unavailable")
        agent.request_id += 1
        request_id = agent.request_id
        try:
            agent.process.stdin.write(
                json.dumps(
                    {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
                )
                + "\n"
            )
            agent.process.stdin.flush()
            deadline = time.monotonic() + 15
            buffered: list[dict[str, Any]] = []
            while time.monotonic() < deadline:
                line = self._read_output_line(agent, deadline - time.monotonic())
                if line is None:
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    self._unlink_auth_barrier(agent)
                    raise CodexRuntimeError("malformed app-server JSON") from exc
                if not isinstance(value, dict):
                    self._unlink_auth_barrier(agent)
                    raise CodexRuntimeError("app-server message is not an object")
                if value.get("id") == request_id and "method" not in value:
                    self._unlink_auth_barrier(agent)
                    if "error" in value:
                        raise self._rpc_error_from_value(method, value.get("error"))
                    result = value.get("result", {})
                    if not isinstance(result, dict) or self._validated_turn_id(self._turn_id(result)) is None:
                        raise CodexRuntimeError("first turn response has no valid turn identity")
                    # Freeze the server-selected turn before replay.  A replayed
                    # terminal/error notification may legitimately transition the
                    # Agent back to idle/failed, and start_task must not overwrite it.
                    turn_id = self._turn_id(result)
                    agent.active_turn_id = turn_id
                    agent.last_started_turn_id = turn_id
                    agent.state = "running"
                    for pending in buffered:
                        self._notification(agent, pending)
                    # Consume any response-following lines already readable before
                    # releasing the reentrant I/O lock. This closes the first-turn
                    # race without inventing a terminal event.
                    if getattr(agent, "runtime_failure", None) is None:
                        self._drain_agent_output_locked(agent)
                    if getattr(agent, "runtime_failure", None) is not None:
                        raise CodexRuntimeError("first turn failed during startup")
                    return result if isinstance(result, dict) else {}
                if "id" in value and isinstance(value.get("method"), str):
                    self._record_notification_header(agent, value)
                    self._unlink_auth_barrier(agent)
                    self._dispatch_server_request(agent, value)
                    continue
                # JSON-RPC responses with another id are not server requests. Keep
                # them as ordinary events and replay once auth is gone.
                buffered.append(value)
            self._unlink_auth_barrier(agent)
            raise CodexRuntimeError(f"app-server did not answer {method}")
        except CodexRuntimeError:
            # Error/timeout paths remove auth but intentionally do not replay buffered
            # notifications; none may reach a model-selected tool before cleanup.
            try:
                self._unlink_auth_barrier(agent)
            except CodexRuntimeError:
                pass
            raise

    def _unlink_auth_barrier(self, agent: _Agent) -> None:
        if not agent.auth_barrier_pending:
            return
        if agent.credential_mode == "provider_proxy":
            agent.auth_barrier_pending = False
            timestamp = time.monotonic()
            agent.provider_proxy_ready_monotonic = timestamp
            self._append_runtime_evidence(
                "auth-barrier",
                {
                    "agent_id": agent.agent_id,
                    "event": "provider_proxy_ready",
                    "monotonic": timestamp,
                },
            )
            return
        path = agent.auth_path
        if path is None:
            raise CodexRuntimeError("first-turn auth barrier has no private path")
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise CodexRuntimeError("private provider auth cleanup failed") from exc
        agent.auth_barrier_pending = False
        timestamp = time.monotonic()
        agent.auth_unlinked_monotonic = timestamp
        self._append_runtime_evidence(
            "auth-barrier",
            {
                "agent_id": agent.agent_id,
                "event": "auth_unlinked",
                "monotonic": timestamp,
            },
        )

    def _record_notification_header(self, agent: _Agent, value: dict[str, Any]) -> None:
        method, params = value.get("method"), value.get("params", {})
        if self._is_progress_notification(value):
            self._reset_activity_clock(agent)
        if isinstance(method, str):
            # R2.3-009 (2026-08-20): the operator explicitly authorized retaining
            # full notification payloads in run evidence, overriding the
            # historical header-only rule, so a live Examiner child-timeout can
            # be attributed step by step (item types plus startedAtMs/
            # completedAtMs) after the child session itself is destroyed.
            # ``param_keys`` stays for backward-compatible readers.
            self._append_runtime_evidence(
                "app-server-events",
                {
                    "agent_id": agent.agent_id,
                    "method": method,
                    "has_request_id": "id" in value,
                    "param_keys": sorted(params) if isinstance(params, dict) else [],
                    "params": params if isinstance(params, dict) else None,
                    **(
                        {"action": "decline", "decision": "decline"}
                        if method
                        in {
                            "item/commandExecution/requestApproval",
                            "item/fileChange/requestApproval",
                            "item/permissions/requestApproval",
                        }
                        and "id" in value
                        else {}
                    ),
                },
            )

    def _dispatch_server_request(self, agent: _Agent, value: dict[str, Any]) -> None:
        """Handle one JSON-RPC ServerRequest exactly once, fail-closed."""

        request_id = value.get("id")
        method = value.get("method")
        params = value.get("params", {})
        if "id" not in value or not isinstance(method, str):
            return
        if method in {
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
            "item/permissions/requestApproval",
        }:
            self._append_runtime_evidence(
                "command-approval-events",
                {
                    "agent_id": agent.agent_id,
                    "method": method,
                    "decision": "decline",
                    "param_keys": sorted(params) if isinstance(params, dict) else [],
                },
            )
            self._respond_server_request(agent, request_id, {"decision": "decline"})
            return
        if method == "item/tool/call" and isinstance(params, dict):
            if (
                getattr(agent, "auth_unlinked_monotonic", None) is not None
                and getattr(agent, "first_dispatch_monotonic", None) is None
            ):
                agent.first_dispatch_monotonic = time.monotonic()
                self._append_runtime_evidence(
                    "auth-barrier",
                    {
                        "agent_id": agent.agent_id,
                        "event": "first_tool_dispatch",
                        "monotonic": agent.first_dispatch_monotonic,
                    },
                )
            self._respond_dynamic_tool(agent, request_id, params)
            return
        if method == "mcpServer/elicitation/request":
            if (
                getattr(agent, "auth_unlinked_monotonic", None) is not None
                and getattr(agent, "first_dispatch_monotonic", None) is None
            ):
                agent.first_dispatch_monotonic = time.monotonic()
                self._append_runtime_evidence(
                    "auth-barrier",
                    {
                        "agent_id": agent.agent_id,
                        "event": "first_mcp_dispatch",
                        "monotonic": agent.first_dispatch_monotonic,
                    },
                )
            schema = params.get("requestedSchema") if isinstance(params, dict) else None
            server_name = str(params.get("serverName", "")) if isinstance(params, dict) else ""
            expected = server_name == "team_transport" or (
                agent.package.role == "protocol" and server_name == "ontology_platform"
            ) or (
                agent.package.role == "protocol"
                and agent.schema_version == 2
                and server_name == "protocol_mechanics"
            ) or (
                agent.package.role == "modeling"
                and self._is_r23003_run(self._active_run)
                and server_name == "modeling_read_proxy"
            ) or (
                bool(self._role_capability_operations(agent.package.role))
                and server_name == "runner_capability"
            ) or (
                agent.package.package_id == "source-examiner"
                and server_name == "examiner_report"
            ) or (
                agent.package.package_id == "platform-examiner"
                and server_name in {"examiner_report", "platform_read_proxy"}
            )
            action = "accept" if expected else "decline"
            self._append_runtime_evidence(
                "mcp-elicitations",
                {
                    "agent_id": agent.agent_id,
                    "server_name": server_name,
                    "mode": str(params.get("mode", "")) if isinstance(params, dict) else "",
                    "schema_keys": sorted(schema) if isinstance(schema, dict) else [],
                    "action": action,
                },
            )
            self._respond_server_request(
                agent, request_id, {"action": action, "content": {}}
            )
            return
        if method == "item/tool/requestUserInput":
            self._append_runtime_evidence(
                "user-input-requests",
                {"agent_id": agent.agent_id, "method": method, "response": "unavailable"},
            )
            self._respond_server_request(agent, request_id, {"answers": {}})
            return
        self._append_runtime_evidence(
            "unknown-server-requests",
            {"agent_id": agent.agent_id, "method": method, "response": "method-not-supported"},
        )
        self._respond_server_error(agent, request_id, -32601, "Method not supported")

    def _drain_agent_output_locked(self, agent: _Agent) -> None:
        """Apply every App Server notification already readable while holding its I/O lock."""
        if agent.process is None or agent.process.stdout is None:
            return
        while True:
            if getattr(agent, "runtime_failure", None) is not None:
                return
            line = self._read_output_line(agent, 0)
            if line is None:
                return
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                with agent.state_lock:
                    agent.state = "failed"
                raise CodexRuntimeError("malformed app-server JSON") from exc
            self._notification(agent, value)
            if getattr(agent, "runtime_failure", None) is not None:
                return

    @staticmethod
    def _read_output_line(agent: _Agent, timeout: float) -> str | None:
        """Read one JSON line without losing TextIO-buffered App Server responses."""
        if agent.process is None or agent.process.stdout is None:
            raise CodexRuntimeError("app-server is unavailable")
        if b"\n" in agent.stdout_buffer:
            line, _, agent.stdout_buffer = agent.stdout_buffer.partition(b"\n")
            return line.decode("utf-8")
        if timeout <= 0:
            readable, _, _ = select.select([agent.process.stdout], [], [], 0)
            if not readable:
                return None
            data = os.read(agent.process.stdout.fileno(), 65536)
            if not data:
                raise CodexRuntimeError("app-server closed its output")
            agent.stdout_buffer += data
            if b"\n" in agent.stdout_buffer:
                line, _, agent.stdout_buffer = agent.stdout_buffer.partition(b"\n")
                return line.decode("utf-8")
            return None
        deadline = time.monotonic() + max(timeout, 0)
        while time.monotonic() < deadline:
            if b"\n" in agent.stdout_buffer:
                line, _, agent.stdout_buffer = agent.stdout_buffer.partition(b"\n")
                return line.decode("utf-8")
            remaining = deadline - time.monotonic()
            readable, _, _ = select.select(
                [agent.process.stdout], [], [], min(remaining, 0.25)
            )
            if not readable:
                continue
            data = os.read(agent.process.stdout.fileno(), 65536)
            if not data:
                raise CodexRuntimeError("app-server closed its output")
            agent.stdout_buffer += data
        return None

    def _initialize(self, agent: _Agent) -> None:
        self._rpc(
            agent,
            "initialize",
            {"clientInfo": {"name": "modeling-team", "version": "1"}},
        )
        # Discovery is a hard preflight, not a structured-input hint.
        self._rpc(agent, "skills/extraRoots/set", {"extraRoots": ["/skills"]})
        listed = self._rpc(
            agent, "skills/list", {"cwds": ["/agent/work"], "forceReload": True}
        )
        entries = listed.get("data", [])
        if not isinstance(entries, list) or len(entries) != 1:
            raise CodexRuntimeError("Skill discovery returned no exact cwd result")
        entry = entries[0]
        if not isinstance(entry, dict) or entry.get("errors"):
            raise CodexRuntimeError("Skill discovery reported an error")
        available = entry.get("skills", [])
        expected = {
            path.parent.name: f"/skills/{path.parent.name}/SKILL.md"
            for path in agent.package.required_skills
        }
        found: dict[str, str] = {}
        for item in available if isinstance(available, list) else []:
            if (
                isinstance(item, dict)
                and item.get("enabled") is True
                and not item.get("error")
            ):
                found[str(item.get("name"))] = str(
                    item.get("path", item.get("canonicalPath", ""))
                )
        if set(found) & set(expected) != set(expected) or any(
            found[name] != path for name, path in expected.items()
        ):
            raise CodexRuntimeError(
                "Skill discovery did not return exact enabled staged paths"
            )
        thread_start_params = {
            "cwd": "/agent/work",
            "baseInstructions": "",
            # Do not leave this null: app-server otherwise retains ambient developer
            # material from the authenticated interactive Codex environment.
            "developerInstructions": agent.package.instructions_path.read_text(
                encoding="utf-8"
            ),
            "config": {
                "web_search": "disabled",
                "default_tools_enabled": False,
                "developer_instructions": agent.package.instructions_path.read_text(
                    encoding="utf-8"
                ),
            },
            "sandbox": self._thread_sandbox(agent),
        }
        if self._coordination_enabled:
            # Formal R2.3-005 binds the App Server's Thread to the same validated
            # role binding that generated config.toml.  Non-formal and archived
            # R2.3-002 starts intentionally keep the legacy request shape (no model).
            thread_start_params["model"] = self._validated_model_override(
                agent.package, formal=True
            ).model
        result = self._rpc(agent, "thread/start", thread_start_params)
        thread_id = (
            result.get("thread", result).get("id") if isinstance(result, dict) else None
        )
        if not isinstance(thread_id, str):
            raise CodexRuntimeError("thread/start lacked Thread identity")
        agent.thread_id, agent.state = thread_id, "idle"
        self._require_expected_mcp_servers(agent)

    def _require_expected_mcp_servers(self, agent: _Agent) -> None:
        """Fail before the first turn unless the frozen per-role MCP surface is live."""
        if agent.package.package_id in {"source-examiner", "platform-examiner"}:
            expected = {"examiner_report": {"submit_examiner_report"}}
            if agent.package.package_id == "platform-examiner":
                expected["platform_read_proxy"] = set(agent.platform_tools)
            self._require_mcp_surface(agent, expected)
            return
        expected = {"team_transport": {"send_team_message", "report_task_result"}}
        if self._coordination_enabled:
            expected["team_transport"].update({"send_coordination", "report_issue"})
            if agent.package.role == "coordinator":
                expected["team_transport"].add("issue_control")
        if agent.package.role == "protocol":
            expected["ontology_platform"] = set(agent.platform_tools)
            if agent.schema_version == 2:
                expected["protocol_mechanics"] = {
                    "build_candidate_receipt",
                    "translate_candidate_to_batches",
                    "verify_scoped_retrieval_fallback",
                }
                if self._coordination_enabled:
                    expected["protocol_mechanics"].add("build_candidate_conflict")
                if agent.proof_gate:
                    expected["protocol_mechanics"].add("write_candidate_item_evidence_map")
        if agent.package.role == "modeling" and self._is_r23003_run(getattr(self, "_active_run", None)):
            expected["modeling_read_proxy"] = set(MODELING_READ_TOOLS)
        capability_operations = self._role_capability_operations(agent.package.role)
        if capability_operations:
            expected["runner_capability"] = set(capability_operations)
        self._require_mcp_surface(agent, expected)

    def _require_lean_examiner_mcp_servers(self, agent: _Agent) -> None:
        """Check the deliberately tiny R2.3-006 surface for all three fresh roles."""

        expected = {"examiner_report": {"submit_examiner_report"}}
        if agent.package.package_id == "platform-examiner":
            expected["platform_read_proxy"] = set(agent.platform_tools)
        self._require_mcp_surface(agent, expected)

    def _require_mcp_surface(self, agent: _Agent, expected: dict[str, set[str]]) -> None:
        """Wait for exactly the MCP servers configured for one child or persistent role."""
        deadline = time.monotonic() + 25
        observed: dict[str, set[str]] = {}
        while time.monotonic() < deadline:
            result = self._rpc(agent, "mcpServerStatus/list", {"detail": "full"})
            data = result.get("data", []) if isinstance(result, dict) else []
            servers = {
                str(item.get("name")): item
                for item in data
                if isinstance(item, dict) and isinstance(item.get("name"), str)
            }
            observed = {}
            for name, item in servers.items():
                observed[name] = self._mcp_tool_names(item.get("tools", []))
            if observed == expected:
                return
            time.sleep(0.25)
        actual = {name: sorted(tools) for name, tools in observed.items()}
        raise CodexRuntimeError(
            f"MCP preflight failed for {agent.agent_id}: expected {sorted(expected)}, got {actual}"
        )

    @staticmethod
    def _mcp_tool_names(raw_tools: Any) -> set[str]:
        """Normalize the object and array forms emitted by app-server status."""
        if isinstance(raw_tools, dict):
            return {
                str(tool.get("name"))
                for tool in raw_tools.values()
                if isinstance(tool, dict)
                and isinstance(tool.get("name"), str)
            }
        if isinstance(raw_tools, list):
            return {
                str(tool.get("name"))
                for tool in raw_tools
                if isinstance(tool, dict) and isinstance(tool.get("name"), str)
            }
        return set()

    def start_task(
        self, agent_id: str, task_text: str, skill_paths: list[str], roster: list[str]
    ) -> None:
        agent = self.agents[agent_id]
        injected = []
        for path in skill_paths:
            source = Path(path)
            staged = f"/skills/{source.parent.name}/SKILL.md"
            injected.append(
                {
                    "type": "skill",
                    "name": source.parent.name,
                    "path": staged,
                }
            )
        prompt = task_text + "\n\nFrozen roster: " + ", ".join(roster)
        agent.first_turn_input = injected + [{"type": "text", "text": prompt}]
        # Retain model-visible material, then verify exact Skills were included.
        if any(not digest_file(Path(path)) for path in skill_paths):
            raise CodexRuntimeError("Skill injection evidence drift")
        result = self._rpc(
            agent,
            "turn/start",
            {"threadId": agent.thread_id, "input": agent.first_turn_input},
        )
        turn_id = self._turn_id(result)
        if getattr(agent, "runtime_failure", None) is not None:
            # A replayed provider error/terminal owns the state; never revive it
            # merely because the synchronous response returned successfully.
            return
        if turn_id is None:
            raise CodexRuntimeError("turn/start response has no valid turn identity")
        with agent.state_lock:
            if agent.state == "idle" and agent.last_completed_turn_id == turn_id:
                return
            if agent.state == "failed":
                return
            agent.active_turn_id = turn_id
            agent.last_started_turn_id = turn_id
            agent.state = "running"
        self._reset_activity_clock(agent)

    @staticmethod
    def _turn_id(result: dict[str, Any]) -> str | None:
        turn = result.get("turn", result)
        return (
            turn.get("id")
            if isinstance(turn, dict) and isinstance(turn.get("id"), str)
            else None
        )

    @staticmethod
    def _extract_platform_report_from_text(agent: Any) -> dict[str, Any] | None:
        """Recover a Platform semantic report from reply text when the tool path fails."""
        deltas = getattr(agent, "message_deltas", None)
        if not isinstance(deltas, dict):
            return None
        text = "".join(
            "".join(parts) if isinstance(parts, (list, tuple)) else str(parts)
            for parts in deltas.values()
        )
        if not text:
            return None
        required = {
            "answerability", "conclusion", "evidence", "coverage", "gaps", "evidence_refs"
        }
        decoder = json.JSONDecoder()
        candidate: dict[str, Any] | None = None
        for index, character in enumerate(text):
            if character != "{":
                continue
            try:
                value, _end = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and required.issubset(value):
                candidate = value
                break
        if candidate is None:
            return None
        if (
            candidate.get("answerability") not in {"answerable", "insufficient-evidence", "unavailable"}
            or not isinstance(candidate.get("conclusion"), str)
            or not candidate.get("conclusion")
            or not isinstance(candidate.get("evidence"), list)
            or not isinstance(candidate.get("gaps"), list)
            or not isinstance(candidate.get("coverage"), dict)
            or not isinstance(candidate.get("evidence_refs"), list)
            or not candidate["evidence_refs"]
        ):
            return None
        return {
            key: candidate[key]
            for key in ("answerability", "conclusion", "evidence", "coverage", "gaps", "evidence_refs")
        }

    @staticmethod
    def _extract_verdict_from_text(agent: Any) -> dict[str, Any] | None:
        """Recover a strict Acceptance verdict from the child's reply text.

        The Acceptance model often writes the verdict in its final message
        instead of calling the submit tool.  Only a complete verdict object
        with the exact seven required fields is accepted; anything else is
        ignored so the typed gate stays authoritative.
        """

        deltas = getattr(agent, "message_deltas", None)
        if not isinstance(deltas, dict):
            return None
        text = "".join(
            "".join(parts) if isinstance(parts, (list, tuple)) else str(parts)
            for parts in deltas.values()
        )
        if not text:
            return None
        required = {"status", "answer", "evidence_ref_ids", "current", "usable", "failure_layer", "blocked_reason"}
        decoder = json.JSONDecoder()
        candidate: dict[str, Any] | None = None
        for index, character in enumerate(text):
            if character != "{":
                continue
            try:
                value, _end = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and required.issubset(value):
                candidate = value
                break
        if candidate is None:
            return None
        if candidate["status"] not in {"PASS", "FAIL", "BLOCKED"}:
            return None
        if not isinstance(candidate["answer"], str) or not candidate["answer"]:
            return None
        if not isinstance(candidate["evidence_ref_ids"], list) or not all(
            isinstance(item, str) and item for item in candidate["evidence_ref_ids"]
        ):
            return None
        if not isinstance(candidate["current"], bool) or not isinstance(candidate["usable"], bool):
            return None
        return {
            key: candidate[key]
            for key in ("status", "answer", "evidence_ref_ids", "current", "usable", "failure_layer", "blocked_reason")
        }

    @staticmethod
    def _expected_active_turn_id(error: str | CodexRuntimeRPCError) -> str | None:
        if isinstance(error, CodexRuntimeRPCError):
            return error.active_turn_id
        # Legacy test seams may still raise the old text-only exception.  Accept
        # only the exact historical wording and validate the captured ID; real
        # App Server responses always use CodexRuntimeRPCError above.
        category, active = CodexRuntimeAdapter._classify_steer_message(
            error if isinstance(error, str) else str(error)
        )
        return active if category == "active_turn_mismatch" else None

    @staticmethod
    def _delivery_input(delivery: RuntimeDelivery) -> list[dict[str, str]]:
        """Render the stable Runner delivery envelope without changing its text field."""
        payload: dict[str, object] = {
            "sender_id": delivery.sender_id,
            "recipient_id": delivery.recipient_id,
            "kind": delivery.kind,
            "text": delivery.text,
            "delivery_id": delivery.delivery_id,
            "expects_reply": delivery.expects_reply,
            "reply_to_delivery_id": delivery.reply_to_delivery_id,
        }
        if delivery.kind == "owner-answer":
            if not isinstance(delivery.owner_answer_id, str) or not delivery.owner_answer_id:
                raise CodexRuntimeError("owner-answer delivery is missing owner_answer_id")
            if not isinstance(delivery.release_id, str) or not delivery.release_id:
                raise CodexRuntimeError("owner-answer delivery is missing release_id")
            payload.update(
                {
                    "owner_answer_id": delivery.owner_answer_id,
                    "release_id": delivery.release_id,
                }
            )
        return [
            {
                "type": "text",
                "text": json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            }
        ]

    def send_message(
        self, agent_id: str, delivery: RuntimeDelivery
    ) -> RuntimeDispatchReceipt:
        # A turn/start notification may be queued before an outer message arrives. Pump it
        # first so turn/steer uses the App Server's active turn identity, not a stale reply.
        self.receive_messages()
        agent = self.agents[agent_id]
        if getattr(agent, "runtime_failure", None) is not None:
            raise CodexRuntimeError("runtime failure is latched")
        if agent.active_turn_id:
            try:
                result = self._rpc(
                    agent,
                    "turn/steer",
                    {
                        "threadId": agent.thread_id,
                        "expectedTurnId": agent.active_turn_id,
                        "input": self._delivery_input(delivery),
                    },
                )
                server_turn_id = self._turn_id(result) or agent.active_turn_id
                if server_turn_id:
                    agent.active_turn_id = server_turn_id
                return RuntimeDispatchReceipt("steer", server_turn_id)
            except CodexRuntimeError as exc:
                # App-server may finish a turn between its notification and our steer.
                # Its explicit rejection means the text was not accepted, so a fresh turn is safe.
                category = (
                    exc.category
                    if isinstance(exc, CodexRuntimeRPCError)
                    else CodexRuntimeAdapter._classify_steer_message(str(exc))[0]
                )
                if category == "no_active_turn_to_steer":
                    agent.active_turn_id, agent.state = None, "idle"
                else:
                    active = self._expected_active_turn_id(exc)
                    if active:
                        # The server explicitly rejected the first request and supplies its
                        # active turn. One retry preserves the text without duplicating it.
                        agent.active_turn_id = active
                        result = self._rpc(
                            agent,
                            "turn/steer",
                            {
                                "threadId": agent.thread_id,
                                "expectedTurnId": agent.active_turn_id,
                                "input": self._delivery_input(delivery),
                            },
                        )
                        server_turn_id = self._turn_id(result) or agent.active_turn_id
                        if server_turn_id:
                            agent.active_turn_id = server_turn_id
                        return RuntimeDispatchReceipt("steer", server_turn_id)
                    states = {item.agent_id: item.state for item in self.get_agent_states()}
                    if states.get(agent_id) == "running":
                        raise
        result = self._rpc(
            agent,
            "turn/start",
            {
                "threadId": agent.thread_id,
                "input": self._delivery_input(delivery),
            },
        )
        agent.active_turn_id, agent.state = self._turn_id(result), "running"
        # A freshly started turn is the activity origin for the inactivity watchdog.
        self._reset_activity_clock(agent)
        return RuntimeDispatchReceipt("start", agent.active_turn_id)

    def _notification(self, agent: _Agent, value: dict[str, Any]) -> None:
        if getattr(agent, "runtime_failure", None) is not None:
            return
        method, params = value.get("method"), value.get("params", {})
        if method == _PROVIDER_ERROR_METHOD:
            self._handle_provider_error_notification(agent, value)
            return
        # Only allowlisted turn/item/tool work counts as live model activity. Error,
        # warning, startup, status, and unknown notices are intentionally ignored.
        self._record_notification_header(agent, value)
        if "id" in value and isinstance(method, str):
            self._dispatch_server_request(agent, value)
            return
        if not isinstance(params, dict):
            return
        with agent.state_lock:
            if method == "item/agentMessage/delta":
                item_id, delta = params.get("itemId"), params.get("delta")
                if isinstance(item_id, str) and isinstance(delta, str):
                    agent.message_deltas.setdefault(item_id, []).append(delta)
            if method in {"item/completed", "item/updated"}:
                self._complete_agent_message(agent, params)
            if method == "item/completed":
                self._record_protocol_platform_artifact(agent, params)
                self._complete_retrieval_gate_item(agent, params)
            if method == "turn/started":
                turn = params.get("turn")
                started_id = turn.get("id") if isinstance(turn, dict) else None
                if self._validated_turn_id(started_id) is None:
                    self._latch_runtime_failure(
                        agent,
                        {"source": "notification", "reason": "turn-identity-invalid", "terminal_method": method},
                    )
                    return
                if agent.active_turn_id is not None and started_id != agent.active_turn_id:
                    self._latch_runtime_failure(
                        agent,
                        {"source": "notification", "reason": "turn-identity-mismatch", "terminal_method": method},
                    )
                    return
                if isinstance(started_id, str):
                    agent.active_turn_id, agent.last_started_turn_id, agent.state = (
                        started_id,
                        started_id,
                        "running",
                    )
            if method in {"turn/completed", "turn/finished"}:
                turn = params.get("turn")
                completed_turn_id = (
                    turn.get("id")
                    if isinstance(turn, dict) and isinstance(turn.get("id"), str)
                    else params.get("turnId")
                    if isinstance(params.get("turnId"), str)
                    else agent.active_turn_id
                )
                # Retain the legacy no-payload terminal projection when no turn
                # is active. A first-turn response always freezes an active ID,
                # so a replayed terminal there remains strictly bound.
                if completed_turn_id is None and agent.active_turn_id is None:
                    agent.active_turn_id, agent.state = None, "idle"
                    return
                if self._validated_turn_id(completed_turn_id) is None:
                    self._latch_runtime_failure(
                        agent,
                        {"source": "notification", "reason": "turn-terminal-invalid", "terminal_method": method},
                    )
                    return
                if agent.active_turn_id is not None and completed_turn_id != agent.active_turn_id:
                    self._latch_runtime_failure(
                        agent,
                        {"source": "notification", "reason": "turn-terminal-mismatch", "terminal_method": method},
                    )
                    return
                if isinstance(completed_turn_id, str):
                    agent.last_completed_turn_id = completed_turn_id
                agent.active_turn_id, agent.state = None, "idle"
            if method in {"turn/failed", "thread/error"}:
                agent.state = "failed"

    def _record_protocol_platform_artifact(
        self, agent: _Agent, params: Mapping[str, Any]
    ) -> None:
        """Send completed Protocol platform MCP results to the Runner sink.

        The app-server notification is the trusted owner of request/result
        bytes.  The Agent can mention a digest in a later handoff, but cannot
        create this registry entry or write the immutable artifact itself.
        """

        if not self._coordination_enabled or self._acceptance is None:
            return
        if agent.package.role != "protocol" or not isinstance(params, Mapping):
            return
        item = params.get("item")
        if not isinstance(item, Mapping):
            return
        if (
            item.get("type") != "mcpToolCall"
            or item.get("server") != "ontology_platform"
            or item.get("status") != "completed"
        ):
            return
        tool = item.get("tool")
        arguments = item.get("arguments")
        if not isinstance(tool, str) or not isinstance(arguments, Mapping) or "result" not in item:
            return
        record = self._acceptance.register_platform_tool_result(
            tool=tool,
            arguments=arguments,
            result=item.get("result"),
        )
        self._append_runtime_evidence("platform-response-artifacts", record)

    def _respond_dynamic_tool(
        self, agent: _Agent, request_id: Any, params: dict[str, Any]
    ) -> None:
        if agent.process is None or agent.process.stdin is None:
            raise CodexRuntimeError("app-server is unavailable")
        tool = params.get("tool")
        arguments = params.get("arguments")
        metadata = self._dynamic_tool_metadata(agent, tool, arguments)
        result = self._dynamic_tool_result(agent, tool, arguments)
        denial_category = self._dynamic_tool_denial_category(tool, arguments, result)
        self._append_runtime_evidence(
            "dynamic-tool-calls",
            {
                **metadata,
                "result": "accepted" if result.get("success") else "rejected",
                "content_item_count": len(result.get("contentItems", [])),
                **({"denial_category": denial_category} if denial_category else {}),
            },
        )
        self._respond_server_request(agent, request_id, result)

    @staticmethod
    def _respond_server_request(agent: _Agent, request_id: Any, result: dict[str, Any]) -> None:
        if agent.process is None or agent.process.stdin is None:
            raise CodexRuntimeError("app-server is unavailable")
        agent.process.stdin.write(
            json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}) + "\n"
        )
        agent.process.stdin.flush()

    @staticmethod
    def _respond_server_error(
        agent: _Agent, request_id: Any, code: int, message: str
    ) -> None:
        if agent.process is None or agent.process.stdin is None:
            raise CodexRuntimeError("app-server is unavailable")
        agent.process.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": code, "message": message},
                }
            )
            + "\n"
        )
        agent.process.stdin.flush()

    def _dynamic_tool_metadata(
        self, agent: _Agent, tool: Any, arguments: Any
    ) -> dict[str, Any]:
        """Persist callback evidence without retaining request text or credentials."""
        agent.dynamic_tool_calls += 1
        safe_arguments = arguments if isinstance(arguments, dict) else {}
        argument_keys = sorted(safe_arguments)
        return {
            "agent_id": agent.agent_id,
            "callback_sequence": agent.dynamic_tool_calls,
            "tool": str(tool).rsplit("__", 1)[-1],
            "argument_keys": argument_keys,
            "argument_types": {
                key: type(value).__name__
                for key, value in safe_arguments.items()
            },
        }

    def _append_runtime_evidence(self, name: str, value: dict[str, Any]) -> None:
        if self._run_root is None:
            return
        evidence = self._run_root / "evidence"
        evidence.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (evidence / f"{name}.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def _dynamic_tool_result(
        self, agent: _Agent, tool: Any, arguments: Any
    ) -> dict[str, Any]:
        """Serve only the read-only files the frozen task exposes to the Agent."""
        transport_tool = str(tool).rsplit("__", 1)[-1]
        if transport_tool in {
            "send_team_message",
            "report_task_result",
            "report_issue",
            "issue_control",
            "send_coordination",
        }:
            if not isinstance(arguments, dict):
                return self._dynamic_tool_error("Team Transport arguments are invalid")
            return self._team_transport_dynamic_result(agent, transport_tool, arguments)
        if tool != "exec" or not isinstance(arguments, dict):
            return self._dynamic_tool_error("unsupported dynamic tool")
        command = arguments.get("cmd", arguments.get("command"))
        if not isinstance(command, str) or not command:
            return self._dynamic_tool_error("dynamic exec requires a command string")
        try:
            tokens = shlex.split(command, posix=True)
        except ValueError:
            return self._dynamic_tool_error("dynamic exec syntax is not permitted")
        if len(tokens) < 2 or tokens[0] != "cat" or any(
            item.startswith("-") for item in tokens[1:]
        ):
            return self._dynamic_tool_error("dynamic exec command is not permitted")
        content: list[str] = []
        remaining = 100000
        for virtual_path in tokens[1:]:
            try:
                value = self._dynamic_read_content(agent, virtual_path)
            except CodexRuntimeError:
                return self._dynamic_tool_error("dynamic exec read failed")
            if value is None:
                return self._dynamic_tool_error("dynamic exec path is not permitted")
            content.append(value[:remaining])
            remaining -= len(content[-1])
            if remaining <= 0:
                break
        return {
            "success": True,
            "contentItems": [{"type": "inputText", "text": "".join(content)}],
        }

    def _dynamic_read_content(self, agent: _Agent, virtual_path: str) -> str | None:
        if virtual_path == "/opt/mechanics-contract.json":
            return self._read_protocol_mechanics_contract(agent)
        staged = self._dynamic_read_path(agent, virtual_path)
        if staged is None:
            return None
        try:
            return staged.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise CodexRuntimeError("dynamic exec read failed") from exc

    def _read_protocol_mechanics_contract(self, agent: _Agent) -> str:
        """Read the sole Protocol /opt asset through one verified descriptor."""
        if self._run_root is None or not isinstance(self._run_id, str) or not self._run_id:
            raise CodexRuntimeError("v2 Protocol mechanics contract has no active run")
        if agent.package.role != "protocol" or self.agents.get(agent.agent_id) is not agent:
            raise CodexRuntimeError("v2 Protocol mechanics contract Agent identity is invalid")
        expected = self._run_root / "runtime-assets" / "protocol" / "mechanics-contract.json"
        if agent.mechanics_contract_path != expected:
            raise CodexRuntimeError("v2 Protocol mechanics contract path is invalid")
        try:
            file_lstat = os.lstat(expected)
            parent_lstat = os.lstat(expected.parent)
            if (
                stat.S_ISLNK(file_lstat.st_mode)
                or stat.S_ISLNK(parent_lstat.st_mode)
                or not stat.S_ISDIR(parent_lstat.st_mode)
                or stat.S_IMODE(parent_lstat.st_mode) != 0o700
                or expected.resolve(strict=True) != expected
            ):
                raise CodexRuntimeError("v2 Protocol mechanics contract path is invalid")
            descriptor = os.open(expected, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError as exc:
            raise CodexRuntimeError("v2 Protocol mechanics contract is unavailable") from exc
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o444:
                raise CodexRuntimeError("v2 Protocol mechanics contract metadata is invalid")
            payload = bytearray()
            while chunk := os.read(descriptor, 65536):
                payload.extend(chunk)
            actual = bytes(payload)
            expected_bytes = protocol_mechanics_contract_bytes(self._run_id)
            if (
                actual != expected_bytes
                or hashlib.sha256(actual).digest() != hashlib.sha256(expected_bytes).digest()
            ):
                raise CodexRuntimeError("v2 Protocol mechanics contract digest is invalid")
            try:
                return actual.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise CodexRuntimeError("v2 Protocol mechanics contract encoding is invalid") from exc
        finally:
            os.close(descriptor)

    @staticmethod
    def _dynamic_read_path(agent: _Agent, virtual_path: str) -> Path | None:
        roots = {
            "/skills/": agent.skills,
            "/agent/home/sources/": agent.home / "sources",
        }
        for prefix, root in roots.items():
            if not virtual_path.startswith(prefix):
                continue
            try:
                resolved = (root / virtual_path.removeprefix(prefix)).resolve(strict=True)
                resolved.relative_to(root.resolve(strict=True))
            except (OSError, ValueError):
                return None
            return resolved if resolved.is_file() else None
        return None

    @staticmethod
    def _dynamic_tool_denial_category(
        tool: Any, arguments: Any, result: dict[str, Any]
    ) -> str | None:
        if result.get("success") or tool != "exec" or not isinstance(arguments, dict):
            return None
        command = arguments.get("cmd", arguments.get("command"))
        if not isinstance(command, str):
            return "invalid-exec"
        if "/proc/" in command:
            return "proc"
        if "/agent/transport/" in command:
            return "broker-socket"
        if "/skills/../" in command or "/agent/home/sources/../" in command:
            return "path-traversal"
        if any(token in command for token in ("curl", "wget", "POST", "PUT", "PATCH")):
            return "platform-write"
        if "/workspaces/" in command or "/runtime/" in command:
            return "host-run-root"
        return "exec-policy"

    def _complete_agent_message(self, agent: _Agent, params: dict[str, Any]) -> None:
        item = params.get("item")
        if not isinstance(item, dict) or item.get("type") != "agentMessage":
            return
        item_id = item.get("id")
        if not isinstance(item_id, str) or item_id in agent.completed_message_ids:
            return
        text = item.get("text")
        if not isinstance(text, str):
            text = "".join(agent.message_deltas.get(item_id, []))
        agent.message_deltas.pop(item_id, None)
        if text:
            agent.completed_message_ids.add(item_id)
            self._messages.append(RuntimeMessage(agent.agent_id, text))

    def _complete_retrieval_gate_item(self, agent: _Agent, params: dict[str, Any]) -> None:
        with agent.state_lock:
            self._complete_retrieval_gate_item_locked(agent, params)

    def _complete_retrieval_gate_item_locked(
        self, agent: _Agent, params: dict[str, Any]
    ) -> None:
        """Advance the v2 fresh-create Protocol retrieval gate from completed MCP items only."""
        if not agent.fallback_eligible:
            return
        item = params.get("item")
        if not isinstance(item, dict) or item.get("type") != "mcpToolCall":
            return
        item_id = item.get("id")
        if not isinstance(item_id, str) or item_id in agent.completed_mcp_item_ids:
            return
        agent.completed_mcp_item_ids.add(item_id)
        server, tool = item.get("server"), item.get("tool")
        if not isinstance(server, str) or not isinstance(tool, str):
            return
        if server == "ontology_platform" and tool == "query_semantic_context":
            self._complete_retrieval_query(agent, item)
            return
        if server == "protocol_mechanics" and tool == "verify_scoped_retrieval_fallback":
            self._complete_retrieval_verifier(agent, item)
            return
        if server == "ontology_platform" and tool in {
            "submit_modeling_batch",
            "run_semantic_validation",
            "run_semantic_reasoning",
        }:
            self._complete_retrieval_mutation(agent, item)

    def _complete_retrieval_query(self, agent: _Agent, item: dict[str, Any]) -> None:
        if item.get("status") not in {"completed", "failed"}:
            return
        arguments = item.get("arguments")
        if not self._eligible_query_arguments(arguments):
            return
        assert isinstance(arguments, dict)
        agent.retrieval_episode += 1
        previous = agent.retrieval_state
        formal = self._formal_mcp_result(item)
        host_receipt_complete = self._host_ordinary_retrieval_complete()
        state = (
            "complete"
            if item.get("status") == "completed"
            and (
                host_receipt_complete
                or self._complete_generic_retrieval(formal, arguments["ontology_ids"])
            )
            else "fallback_required"
        )
        agent.retrieval_state = state
        self._record_retrieval_transition(
            agent,
            tool="query_semantic_context",
            previous=previous,
            current=state,
            reason=(
                "host_receipt_complete"
                if host_receipt_complete and state == "complete"
                else "generic_complete"
                if state == "complete"
                else "fallback_required"
            ),
        )

    def _host_ordinary_retrieval_complete(self) -> bool:
        """Read the Runner-owned ordinary receipt without re-evaluating its evidence.

        The Host carrier is the only component allowed to validate the accepted
        candidate's path/binding/paging receipt.  Runtime adapters may use its
        typed completion marker to avoid applying the older aggregate-warning
        heuristic a second time.  A missing receipt keeps the legacy gate intact.
        """

        if not self._coordination_enabled or self._acceptance is None:
            return False
        receipt = getattr(self._acceptance, "ordinary_retrieval_receipt", None)
        if not isinstance(receipt, Mapping):
            return False
        return receipt.get("schema_version") == ORDINARY_RETRIEVAL_RECEIPT_SCHEMA

    def _complete_retrieval_verifier(self, agent: _Agent, item: dict[str, Any]) -> None:
        previous = agent.retrieval_state
        if previous not in {"fallback_required", "complete"}:
            return
        arguments = item.get("arguments")
        result = item.get("result")
        complete, category = self._native_verifier_completion(item, result)
        self._append_runtime_evidence(
            "native-verifier-events",
            {
                "role": agent.package.role,
                "tool": "verify_scoped_retrieval_fallback",
                "status": "accepted" if complete else "rejected",
                "complete": complete,
                "proof_arguments_sha256": self._safe_json_digest(arguments),
                "result_envelope_sha256": self._safe_json_digest(result),
                "category": category,
                "recorded_at_ns": time.time_ns(),
            },
        )
        if not complete:
            return
        if previous == "fallback_required":
            agent.retrieval_state = "fallback_satisfied"
            self._record_retrieval_transition(
                agent,
                tool="verify_scoped_retrieval_fallback",
                previous=previous,
                current="fallback_satisfied",
                reason="verifier_completed",
            )

    @staticmethod
    def _safe_json_digest(value: object) -> str:
        try:
            payload = json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise CodexRuntimeError("native verifier event payload is not JSON") from exc
        return hashlib.sha256(payload).hexdigest()

    @classmethod
    def _native_verifier_completion(
        cls, item: dict[str, Any], result: object
    ) -> tuple[bool, str]:
        """Classify only an actual native verifier completion, without retaining its payload."""
        if item.get("status") != "completed":
            return False, "failed"
        if not isinstance(item.get("arguments"), dict):
            return False, "invalid_arguments"
        if "error" in item:
            return False, "protocol_error"
        if not isinstance(result, dict) or result.get("isError") is True or "error" in result:
            return False, "protocol_error"
        structured = result.get("structuredContent")
        if not isinstance(structured, dict):
            return False, "invalid_envelope"
        if structured.get("ok") is True:
            data = structured.get("data")
            if not isinstance(data, dict):
                return False, "invalid_envelope"
            return (True, "complete") if data.get("complete") is True else (False, "incomplete")
        # The native stdio facade projects its successful `{complete: true, ...}`
        # result directly as structuredContent.  Keep accepting that real result
        # shape while rejecting any missing/false completion marker.
        if structured.get("complete") is True and "error" not in structured:
            return True, "complete"
        return False, "incomplete"

    def _complete_retrieval_mutation(self, agent: _Agent, item: dict[str, Any]) -> None:
        if item.get("status") != "completed":
            return
        tool = item.get("tool")
        arguments = item.get("arguments")
        if tool == "submit_modeling_batch" and (
            not isinstance(arguments, dict) or arguments.get("mode") != "apply_atomic"
        ):
            return
        formal = self._formal_mcp_result(item)
        if not self._formal_success(formal):
            return
        previous = agent.retrieval_state
        agent.retrieval_state = "query_required"
        self._record_retrieval_transition(
            agent,
            tool=tool,
            previous=previous,
            current="query_required",
            reason="semantic_state_changed",
        )

    @staticmethod
    def _eligible_query_arguments(arguments: object) -> bool:
        if not isinstance(arguments, dict) or arguments.get("scope_mode") != "ontologies":
            return False
        ontology_ids = arguments.get("ontology_ids")
        return isinstance(ontology_ids, list) and bool(ontology_ids) and all(
            isinstance(ontology_id, str) and bool(ontology_id.strip()) for ontology_id in ontology_ids
        )

    @staticmethod
    def _formal_mcp_result(item: dict[str, Any]) -> dict[str, Any] | None:
        result = item.get("result")
        if not isinstance(result, dict):
            return None
        structured = result.get("structuredContent")
        if isinstance(structured, dict):
            return structured
        return None

    @staticmethod
    def _formal_success(value: object) -> bool:
        return isinstance(value, dict) and value.get("ok") is True and isinstance(value.get("data"), dict)

    def _complete_generic_retrieval(
        self, formal: dict[str, Any] | None, requested_ontology_ids: object
    ) -> bool:
        if not self._formal_success(formal) or not isinstance(requested_ontology_ids, list):
            return False
        assert formal is not None
        data = formal["data"]
        if data.get("result_status") != "matched":
            return False
        recall, matches_page, context_page = (
            data.get("recall"),
            data.get("matches_page"),
            data.get("context_page"),
        )
        if (
            not isinstance(recall, dict)
            or recall.get("completeness") != "complete"
            or data.get("truncated") is not False
            or not isinstance(matches_page, dict)
            or matches_page.get("truncated") is not False
            or matches_page.get("next_match_cursor") is not None
            or not isinstance(context_page, dict)
            or context_page.get("truncated") is not False
            or context_page.get("next_context_cursor") is not None
        ):
            return False
        requested = set(requested_ontology_ids)
        if not requested or not self._warnings_are_complete(data.get("warnings")):
            return False
        for collection in (data.get("primary_matches"), data.get("related_context")):
            if not isinstance(collection, list):
                return False
            for item in collection:
                if not isinstance(item, dict) or item.get("ontology_id") not in requested:
                    return False
                if item.get("assertion_kind") == "asserted" and item.get("evidence_status") != "supported":
                    return False
                lineage = item.get("lineage")
                if not isinstance(lineage, dict) or lineage.get("status") != "complete":
                    return False
                if not self._warnings_are_complete(item.get("warnings")):
                    return False
        return True

    @staticmethod
    def _warnings_are_complete(warnings: object) -> bool:
        if not isinstance(warnings, list):
            return False
        for warning in warnings:
            if not isinstance(warning, dict) or not isinstance(warning.get("code"), str):
                return False
            if warning["code"] in _RETRIEVAL_BLOCKING_WARNINGS:
                return False
        return True

    def _record_retrieval_transition(
        self,
        agent: _Agent,
        *,
        tool: object,
        previous: str,
        current: str,
        reason: str,
    ) -> None:
        self._append_runtime_evidence(
            "protocol-retrieval-gate",
            {
                "agent_id": agent.agent_id,
                "tool": str(tool),
                "episode": agent.retrieval_episode,
                "from": previous,
                "to": current,
                "reason": reason,
            },
        )

    def terminal_report_blocked(
        self,
        agent_id: str,
        already_synchronized: bool = False,
        status: str = "completed",
    ) -> bool:
        """Synchronize pending Agent output before the Broker decides a terminal report."""
        agent = self.agents.get(agent_id)
        if agent is None:
            return False
        if already_synchronized is not True:
            if not agent.io_lock.acquire(blocking=False):
                return True
            try:
                self._drain_agent_output_locked(agent)
            except Exception:
                return True
            finally:
                agent.io_lock.release()
        with agent.state_lock:
            blocked = (
                status == "completed"
                and agent.fallback_eligible
                and agent.retrieval_state in {
                    "fallback_required",
                    "query_required",
                }
                and not self._host_ordinary_retrieval_complete()
            )
            if blocked:
                self._record_retrieval_transition(
                    agent,
                    tool="report_task_result",
                    previous=agent.retrieval_state,
                    current=agent.retrieval_state,
                    reason="terminal_blocked",
                )
            return blocked

    def _team_transport_dynamic_result(
        self, agent: _Agent, tool: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute only frozen Profile transport tools through the Agent-owned socket."""
        request = {"method": "tools/call", "params": {"name": tool, "arguments": arguments}}
        if tool == "report_task_result":
            # This request originates inside ordered App Server notification dispatch.  It alone
            # has already synchronized stdout before the Broker calls the Runtime guard.
            request["already_synchronized"] = True
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(10)
                connection.connect(str(self._transport_root() / f"{agent.agent_id}.sock"))
                connection.sendall((json.dumps(request, ensure_ascii=False) + "\n").encode())
                response = connection.makefile("r", encoding="utf-8").readline(4097)
            if len(response) > 4096:
                return self._dynamic_tool_error("Team Transport rejected the request")
            result = json.loads(response)
        except (OSError, ValueError, json.JSONDecodeError):
            return self._dynamic_tool_error("Team Transport is unavailable")
        if not isinstance(result, dict):
            if tool == "report_task_result":
                self._append_runtime_evidence(
                    "team-transport-events",
                    {
                        "agent": agent.agent_id,
                        "tool": "report_task_result",
                        "status": "rejected",
                        "category": "transport_protocol_error",
                        "ack": "not_applicable",
                        "recorded_at_ns": time.time_ns(),
                    },
                )
            return self._dynamic_tool_error("Team Transport rejected the request")
        if "error" in result:
            error = self._safe_transport_error(agent, result["error"])
            if error is None:
                if tool == "report_task_result":
                    self._append_runtime_evidence(
                        "team-transport-events",
                        {
                            "agent": agent.agent_id,
                            "tool": "report_task_result",
                            "status": "rejected",
                            "category": "untrusted_broker_error",
                            "ack": "not_applicable",
                            "recorded_at_ns": time.time_ns(),
                        },
                    )
                return self._dynamic_tool_error("Team Transport rejected the request")
            if tool == "report_task_result":
                category = (
                    "missing_modeling_handoff"
                    if error.startswith("terminal result requires terminal handoffs: ")
                    and "modeling" in error.rsplit(": ", 1)[-1].split(", ")
                    else "broker_rejection"
                )
                self._append_runtime_evidence(
                    "team-transport-events",
                    {
                        "agent": agent.agent_id,
                        "tool": "report_task_result",
                        "status": "rejected",
                        "category": category,
                        "ack": "not_applicable",
                        "recorded_at_ns": time.time_ns(),
                    },
                )
            return self._dynamic_tool_error(f"Team Transport rejected the request: {error}")
        if tool == "report_task_result":
            self._append_runtime_evidence(
                "team-transport-events",
                {
                    "agent": agent.agent_id,
                    "tool": "report_task_result",
                    "status": "accepted",
                    "category": "terminal_report_accepted",
                    "ack": "not_applicable",
                    "recorded_at_ns": time.time_ns(),
                },
            )
        return {
            "success": True,
            "contentItems": [{"type": "inputText", "text": json.dumps(result)}],
        }

    def _safe_transport_error(self, agent: _Agent, value: object) -> str | None:
        """Accept only fixed broker RoutingError text; never reflect socket-controlled data."""
        if not isinstance(value, str) or len(value) > 200:
            return None
        fixed = {
            TERMINAL_REPORT_GUARD_ERROR,
            "recipient is not allowed by frozen Profile",
            "terminal result is invalid",
            "Agent already reported a terminal result",
            "terminal result dependencies are invalid",
            "unsupported Team Transport request",
            "invalid Team Transport arguments",
            "unknown Team Transport tool",
            "terminal result requires delivered reply",
            "completed terminal result requires an established reply request",
            "Team Transport reply arguments are invalid",
            "Team Transport reply is not an active reversed request",
            "Team Transport delivery acknowledgement is invalid",
            "Team Transport reply acknowledgement is invalid",
            "terminal handoff acknowledgement is invalid",
            "issue escalation capability is unavailable",
            "issue reporter is not allowed by frozen Profile",
            "issue control is Coordinator-only",
            "an active issue already exists",
            "terminal result is blocked by an active issue",
            "issue callback enqueue failed",
            "issue control epoch is stale",
            "issue pause is not valid in current state",
            "issue resume requires persisted resolution",
            "issue resume resolution does not match persisted resolution",
            "resume control cannot carry an abort resolution",
            "issue abort requires a persisted outer abort resolution",
            "issue abort reason does not match persisted resolution",
            "issue is already terminal",
            "issue resolution replay conflicts",
            "issue resolution was already persisted",
            "issue resolution is not valid in current state",
            "unknown mutation state requires formal reconciliation",
        }
        if value in fixed:
            return value
        prefix = "terminal result requires terminal handoffs: "
        if not value.startswith(prefix):
            return None
        if agent.package.role not in {"coordinator", "protocol"} or self.agents.get(agent.agent_id) is not agent:
            return None
        expected: list[str] = []
        dependency_roles = ("modeling", "protocol") if agent.package.role == "coordinator" else ("modeling",)
        for role in dependency_roles:
            matching = [
                candidate.agent_id
                for candidate in self.agents.values()
                if candidate.package.role == role
            ]
            if len(matching) != 1:
                return None
            expected.extend(matching)
        expected_count = 2 if agent.package.role == "coordinator" else 1
        if len(set(expected)) != expected_count:
            return None
        role_names = value[len(prefix) :].split(", ")
        if ", ".join(role_names) != value[len(prefix) :]:
            return None
        return value if role_names == sorted(expected) else None

    @staticmethod
    def _dynamic_tool_error(message: str) -> dict[str, Any]:
        return {
            "success": False,
            "contentItems": [{"type": "inputText", "text": message}],
        }

    def receive_messages(self) -> list[RuntimeMessage]:
        sessions = self._provider_sessions
        if self._coordination_enabled and sessions is not None:
            if not sessions.listening():
                self._on_provider_session_failure("provider-upstream-failed")
        for agent in self.agents.values():
            try:
                with agent.io_lock:
                    self._drain_agent_output_locked(agent)
            except CodexRuntimeError:
                # A provider failure owns the first terminal cause; process-group
                # termination may close stdout before Runner consumes its typed
                # queue. Preserve that cause and suppress only this secondary EOF.
                if getattr(agent, "runtime_failure", None) is None:
                    raise
        values, self._messages = self._messages[:], []
        return values

    def get_agent_states(self) -> list[AgentState]:
        return [
            AgentState(
                key,
                value.state,
                value.last_started_turn_id,
                value.last_completed_turn_id,
            )
            for key, value in self.agents.items()
        ]

    def last_output_monotonic(self) -> float:
        """Most recent App Server notification timestamp across all roles.

        Read by the Runner's cooperative idle inquiry (R2.3-009 start10/12):
        when no role has emitted any notification and no turn is running, the
        run is idle between phases and the Coordinator is nudged.  Returns
        ``0.0`` before any role has produced output; callers must seed their
        own baseline at run start.
        """
        return max(
            (agent.last_output_monotonic for agent in self.agents.values()),
            default=0.0,
        )

    def wait_settled(self, agent_ids: list[str], timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if all(
                self.agents[key].state not in {"starting", "running"}
                for key in agent_ids
            ):
                return True
            time.sleep(0.05)
        return False

    def pause(self) -> None:
        for agent in self.agents.values():
            if agent.active_turn_id:
                self._rpc(
                    agent,
                    "turn/interrupt",
                    {"threadId": agent.thread_id, "turnId": agent.active_turn_id},
                )
                agent.state = "idle"

    def resume(self) -> None:
        return None

    def _record_cleanup_error(self, identity: str, reason_code: str) -> None:
        """Retain only a fixed, safe cleanup failure projection."""

        if not isinstance(identity, str) or not identity:
            identity = "runtime"
        allowed = {
            "child-stop-failed",
            "child-destroy-failed",
            "role-stop-failed",
            "role-unlink-failed",
            "role-residual-check-failed",
            "stderr-drain-failed",
            "proxy-stop-failed",
            "aggregate-audit-failed",
        }
        if reason_code not in allowed:
            reason_code = "cleanup-failed"
        self._cleanup_errors.setdefault(
            identity,
            {"category": "runtime/infrastructure", "reason_code": reason_code},
        )

    def _stop_child_for_cleanup(
        self,
        handle_digest: str,
        resource: Any,
        process_surfaces: list[tuple[str, bytes | None]],
        roots: list[Path],
    ) -> None:
        identity = f"child:{handle_digest}"
        spec = getattr(resource, "spec", None)
        if isinstance(spec, dict):
            private_root = spec.get("private_root")
            if isinstance(private_root, str) and private_root:
                roots.append(Path(private_root))
        child_agent = getattr(resource, "_child_agent", None)
        if isinstance(child_agent, _Agent):
            self._child_auth_barriers[identity] = {
                "auth_unlinked_monotonic": child_agent.auth_unlinked_monotonic,
                "provider_proxy_ready_monotonic": child_agent.provider_proxy_ready_monotonic,
                "first_dispatch_monotonic": child_agent.first_dispatch_monotonic,
            }
        try:
            stop = getattr(resource, "stop", None)
            if callable(stop):
                stop()
        except Exception:
            self._record_cleanup_error(identity, "child-stop-failed")
        try:
            destroy = getattr(resource, "destroy", None)
            if callable(destroy):
                destroy()
        except Exception:
            self._record_cleanup_error(identity, "child-destroy-failed")
        if isinstance(child_agent, _Agent):
            try:
                process_surfaces.extend(self._process_surface_payloads(child_agent))
            except Exception:
                self._record_cleanup_error(identity, "child-stop-failed")
        # A resource that did not reach ``destroyed`` remains registered so
        # cleanup evidence cannot claim zero active child residue.
        if bool(getattr(resource, "destroyed", False)):
            self._acceptance_children.pop(handle_digest, None)

    def _stop_agent_for_cleanup(
        self,
        agent: _Agent,
        artifact_names: tuple[str, ...],
        process_surfaces: list[tuple[str, bytes | None]],
    ) -> bool:
        cleanup_ok = True
        try:
            agent.inactivity_watchdog_stop.set()
            self._close_retrieval_asset_fds(agent)
            process = agent.process
            if process is not None and process.poll() is None:
                try:
                    pid = getattr(process, "pid", None)
                    if isinstance(pid, int) and pid > 0:
                        os.killpg(os.getpgid(pid), signal.SIGTERM)
                    else:
                        process.terminate()
                except (ProcessLookupError, PermissionError, OSError):
                    terminate = getattr(process, "terminate", None)
                    if callable(terminate):
                        terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        pid = getattr(process, "pid", None)
                        if isinstance(pid, int) and pid > 0:
                            os.killpg(os.getpgid(pid), signal.SIGKILL)
                        else:
                            process.kill()
                    except (ProcessLookupError, PermissionError, OSError):
                        kill = getattr(process, "kill", None)
                        if callable(kill):
                            kill()
                    process.wait(timeout=5)
        except Exception:
            cleanup_ok = False
            self._record_cleanup_error(agent.agent_id, "role-stop-failed")
        try:
            process_surfaces.extend(self._process_surface_payloads(agent))
        except Exception:
            cleanup_ok = False
            self._record_cleanup_error(agent.agent_id, "role-stop-failed")
        if agent.stderr_drain is not None:
            try:
                agent.stderr_drain.stop()
                self._stderr_drain_reports[agent.agent_id] = agent.stderr_drain.snapshot()
                if agent.stderr_drain.lifecycle_failure:
                    self._stderr_drain_failures[agent.agent_id] = {
                        "category": "runtime/infrastructure",
                        "reason_code": "stderr-drain-failed",
                    }
                    self._record_cleanup_error(agent.agent_id, "stderr-drain-failed")
            except Exception:
                cleanup_ok = False
                self._record_cleanup_error(agent.agent_id, "stderr-drain-failed")
        if agent.auth_path is not None and agent.credential_mode != "provider_proxy":
            try:
                agent.auth_path.unlink(missing_ok=True)
            except OSError:
                cleanup_ok = False
                self._record_cleanup_error(agent.agent_id, "role-unlink-failed")
        for name in artifact_names:
            try:
                (agent.home / name).unlink(missing_ok=True)
            except OSError:
                cleanup_ok = False
                self._record_cleanup_error(agent.agent_id, "role-unlink-failed")
        try:
            residual = any(
                (agent.home / name).exists() or (agent.home / name).is_symlink()
                for name in artifact_names
            )
        except OSError:
            residual = True
            cleanup_ok = False
            self._record_cleanup_error(agent.agent_id, "role-residual-check-failed")
        if residual:
            cleanup_ok = False
        agent.state = "stopped"
        return cleanup_ok

    def _build_formal_cleanup_aggregate(
        self,
        roots: list[Path],
        process_surfaces: list[tuple[str, bytes | None]],
        *,
        secret_values: tuple[bytes, ...] | None = None,
    ) -> dict[str, Any]:
        """Perform the one final formal run-wide audit after runtime teardown.

        Provider credentials are captured before the proxy is stopped and passed
        in explicitly.  The audit itself must run only after child/role
        artifacts and the provider proxy have been stopped, so its result
        reflects the final cleanup state rather than a pre-cleanup snapshot.
        """

        if self._formal_cleanup_aggregate is not None:
            return deepcopy(self._formal_cleanup_aggregate)
        try:
            values = self._secret_values_for_audit() if secret_values is None else secret_values
            result = audit_private_artifacts(
                roots,
                values,
                process_surfaces=process_surfaces,
            )
            safe_audit = self._safe_cleanup_audit(result)
        except Exception:
            safe_audit = {
                "scanned_files": 0,
                "match_count": 1,
                "matched_secret_count": 1,
                "scan_complete": False,
                "scan_error_count": 1,
            }
            self._record_cleanup_error("aggregate", "aggregate-audit-failed")
        self._formal_cleanup_aggregate = {
            "private_credentials_destroyed": False,
            "secret_audit": safe_audit,
            "scanned_files": int(safe_audit["scanned_files"]),
            "match_count": int(safe_audit["match_count"]),
            "matched_secret_count": int(safe_audit["matched_secret_count"]),
            "scan_complete": bool(safe_audit["scan_complete"]),
            "scan_error_count": int(safe_audit["scan_error_count"]),
            "active_resources": False,
            "zero_child_residue": not bool(self._acceptance_children),
            "cleanup_error_count": len(self._cleanup_errors),
        }
        return deepcopy(self._formal_cleanup_aggregate)

    def _stop_locked(self) -> None:
        formal = self._coordination_enabled
        artifact_names = _PRIVATE_AGENT_BASE_ARTIFACT_NAMES
        if formal:
            artifact_names += _PRIVATE_FORMAL_AGENT_ARTIFACT_NAMES
        roots: list[Path] = []
        if self._run_root is not None:
            roots.append(self._run_root)
        process_surfaces: list[tuple[str, bytes | None]] = []
        for handle_digest, resource in list(self._acceptance_children.items()):
            try:
                self._stop_child_for_cleanup(handle_digest, resource, process_surfaces, roots)
            except Exception:
                self._record_cleanup_error(f"child:{handle_digest}", "child-stop-failed")
            if not formal:
                # Legacy cleanup always removed the registry handle in its
                # ``finally`` block; formal cleanup retains failed-destroy
                # handles so residue cannot be hidden.
                self._acceptance_children.pop(handle_digest, None)
        for agent in list(self.agents.values()):
            if formal:
                roots.extend((agent.home, agent.work, agent.skills))
            if not formal:
                # Legacy cleanup keeps its per-role evidence shape and audit
                # timing; formal runs use only the aggregate below.
                self._record_cleanup_audit(
                    agent.agent_id,
                    self._audit_process_surfaces(agent),
                    suppress_secret_digests=False,
                )
            try:
                cleanup_ok = self._stop_agent_for_cleanup(agent, artifact_names, process_surfaces)
            except Exception:
                cleanup_ok = False
                self._record_cleanup_error(agent.agent_id, "role-stop-failed")
                agent.state = "stopped"
            if not formal:
                post_audit = audit_private_artifacts(
                    self._run_root if self._run_root is not None else agent.home,
                    self._secret_values_for_audit(),
                )
                self._record_cleanup_audit(agent.agent_id, post_audit)
                self._private_credentials_destroyed[agent.agent_id] = (
                    cleanup_ok
                    and agent.agent_id not in self._secret_audit_failures
                    and agent.agent_id not in self._stderr_drain_failures
                )
        if formal:
            # Snapshot provider credentials while the sessions still own them;
            # the formal audit itself is intentionally deferred until after
            # session shutdown and secret clearing below.
            try:
                audit_secret_values = self._secret_values_for_audit()
            except Exception:
                audit_secret_values = ()
                self._record_cleanup_error("aggregate", "aggregate-audit-failed")
            sessions_failed = False
            sessions = self._provider_sessions
            counters: dict[str, dict[str, Any]] = {}
            try:
                if sessions is not None:
                    counters = {
                        provider_id: dict(snapshot)
                        for provider_id, snapshot in sorted(sessions.snapshot().items())
                    }
                    # Every referenced session is independently stopped and
                    # wiped; one failure cannot skip the others.
                    reports = sessions.stop()
                    self._provider_stop_status = {
                        provider_id: dict(report)
                        for provider_id, report in reports.items()
                        if isinstance(report, Mapping)
                    }
                    sessions_failed = any(
                        bool(report.get("lifecycle_failure"))
                        for report in self._provider_stop_status.values()
                    )
            except Exception:
                sessions_failed = True
            finally:
                if sessions_failed:
                    self._record_cleanup_error("provider-sessions", "provider-session-cleanup-failed")
                    self._on_provider_session_failure("provider-session-cleanup-failed")
                self._provider_sessions = None
                # Each session owns its mutable key; this list owns only audit
                # sentinels.  Both are released at the outer lifecycle edge.
                self._secret_audit_values.clear()
            aggregate = self._build_formal_cleanup_aggregate(
                roots,
                process_surfaces,
                secret_values=audit_secret_values,
            )
            aggregate["providers"] = {
                provider_id: {
                    "counters": counters.get(provider_id, {}),
                    "stop": dict(self._provider_stop_status.get(provider_id, {})),
                }
                for provider_id in sorted(
                    set(counters) | set(self._provider_stop_status)
                )
            }
            aggregate["scanned_files"] = int(aggregate["secret_audit"]["scanned_files"])
            aggregate["match_count"] = int(aggregate["secret_audit"]["match_count"])
            aggregate["matched_secret_count"] = int(
                aggregate["secret_audit"]["matched_secret_count"]
            )
            aggregate["cleanup_error_count"] = len(self._cleanup_errors)
            aggregate["zero_child_residue"] = not bool(self._acceptance_children)
            aggregate["private_credentials_destroyed"] = (
                bool(aggregate["scan_complete"])
                and int(aggregate["scan_error_count"]) == 0
                and int(aggregate["secret_audit"]["match_count"]) == 0
                and int(aggregate["secret_audit"]["matched_secret_count"]) == 0
                and bool(aggregate["zero_child_residue"])
                and not self._cleanup_errors
                and not sessions_failed
            )
            self._formal_cleanup_aggregate = deepcopy(aggregate)
            for agent in self.agents.values():
                self._private_credentials_destroyed[agent.agent_id] = bool(
                    aggregate["private_credentials_destroyed"]
                )
        else:
            self._provider_sessions = None
            self._secret_audit_values.clear()

    def stop(self) -> None:
        with self._cleanup_lock:
            if self._cleanup_snapshot is not None:
                return
            try:
                self._stop_locked()
            except Exception:
                self._record_cleanup_error("runtime", "cleanup-failed")
            finally:
                # The session/key boundary is outermost: even an unexpected
                # child/role cleanup exception cannot leave a provider key in
                # memory.  The normal formal path already stopped and detached
                # the sessions; this is the fail-closed fallback for partial stop.
                sessions = self._provider_sessions
                if self._coordination_enabled and sessions is not None:
                    try:
                        reports = sessions.stop()
                        if isinstance(reports, Mapping):
                            self._provider_stop_status.update(
                                {
                                    provider_id: dict(report)
                                    for provider_id, report in reports.items()
                                    if isinstance(report, Mapping)
                                }
                            )
                            if any(
                                bool(report.get("lifecycle_failure"))
                                for report in reports.values()
                                if isinstance(report, Mapping)
                            ):
                                self._record_cleanup_error(
                                    "provider-sessions", "provider-session-cleanup-failed"
                                )
                    except Exception:
                        self._record_cleanup_error(
                            "provider-sessions", "provider-session-cleanup-failed"
                        )
                    self._provider_sessions = None
                if self._coordination_enabled:
                    self._secret_audit_values.clear()
                    if self._formal_cleanup_aggregate is not None and self._cleanup_errors:
                        aggregate = deepcopy(self._formal_cleanup_aggregate)
                        aggregate["private_credentials_destroyed"] = False
                        aggregate["cleanup_error_count"] = len(self._cleanup_errors)
                        self._formal_cleanup_aggregate = aggregate
                        for agent in self.agents.values():
                            self._private_credentials_destroyed[agent.agent_id] = False
                # A cleanup exception must not make a subsequent caller repeat
                # destructive work.  The projection below records any safe
                # error and remains immutable for the lifecycle.
                self._cleanup_snapshot = self._build_cleanup_projection()

    def _build_cleanup_projection(self) -> dict[str, Any]:
        formal = self._coordination_enabled
        identifiers = {}
        artifact_names = _PRIVATE_AGENT_BASE_ARTIFACT_NAMES
        if formal:
            artifact_names += _PRIVATE_FORMAL_AGENT_ARTIFACT_NAMES
        for key, value in self.agents.items():
            stderr_drain = dict(
                self._stderr_drain_reports.get(
                    key,
                    {
                        "bytes_drained": 0,
                        "match_count": 0,
                        "lifecycle_failure": False,
                    },
                )
            )
            if key in self._stderr_drain_failures:
                stderr_drain.update(self._stderr_drain_failures[key])
            private_credentials_destroyed = self._private_credentials_destroyed.get(key, False)
            if private_credentials_destroyed and self._cleanup_snapshot is None:
                private_credentials_destroyed = not any(
                    (value.home / name).exists() or (value.home / name).is_symlink()
                    for name in artifact_names
                )
            if formal:
                aggregate_audit = (
                    self._formal_cleanup_aggregate.get("secret_audit")
                    if self._formal_cleanup_aggregate is not None
                    else None
                )
                default_audit = deepcopy(aggregate_audit) if isinstance(aggregate_audit, dict) else {
                    "scanned_files": 0,
                    "match_count": 0,
                    "matched_secret_count": 0,
                    "scan_complete": False,
                    "scan_error_count": 1,
                }
            else:
                default_audit = {
                    "scanned_files": 0,
                    "match_count": 0,
                    "matched_secret_count": 0,
                    "matched_secret_digests": [],
                }
            raw_audit = self._secret_audit_failures.get(key)
            projected_audit = (
                self._safe_cleanup_audit(raw_audit)
                if formal and isinstance(raw_audit, Mapping)
                else raw_audit or default_audit
            )
            identifiers[key] = {
                "thread_id": value.thread_id,
                "pid": getattr(value.process, "pid", None) if value.process else None,
                "auth_barrier": {
                    "auth_unlinked_monotonic": value.auth_unlinked_monotonic,
                    "provider_proxy_ready_monotonic": value.provider_proxy_ready_monotonic,
                    "first_dispatch_monotonic": value.first_dispatch_monotonic,
                },
                "private_credentials_destroyed": private_credentials_destroyed,
                "secret_audit": projected_audit,
                "stderr_drain": stderr_drain,
            }
            if formal and key in self._cleanup_errors:
                identifiers[key]["cleanup_error"] = dict(self._cleanup_errors[key])
        children = {
            "active": len(self._acceptance_children),
            "zero_residue": not self._acceptance_children,
            "auth_barriers": deepcopy(self._child_auth_barriers),
            "stderr_drain": {
                key: value
                for key, value in self._stderr_drain_reports.items()
                if key.startswith("source-examiner-")
                or key.startswith("platform-examiner-")
            },
            "secret_audit": (
                {
                    key: self._safe_cleanup_audit(value)
                    for key, value in self._secret_audit_failures.items()
                    if key.startswith("child:") and isinstance(value, Mapping)
                }
                if formal
                else {
                    key: value
                    for key, value in self._secret_audit_failures.items()
                    if key.startswith("child:")
                }
            ),
        }
        if formal:
            children["errors"] = {
                key: dict(value)
                for key, value in self._cleanup_errors.items()
                if key.startswith("child:")
            }
        projection = identifiers | {"acceptance_children": children}
        if formal:
            aggregate = deepcopy(
                self._formal_cleanup_aggregate
                if self._formal_cleanup_aggregate is not None
                else {
                    "private_credentials_destroyed": False,
                    "secret_audit": {
                        "scanned_files": 0,
                        "match_count": 0,
                        "matched_secret_count": 0,
                        "scan_complete": False,
                        "scan_error_count": 1,
                    },
                    "scanned_files": 0,
                    "match_count": 0,
                    "matched_secret_count": 0,
                    "scan_complete": False,
                    "scan_error_count": 1,
                    "active_resources": bool(self._lifecycle_has_active_resources()),
                    "zero_child_residue": not bool(self._acceptance_children),
                    "cleanup_error_count": len(self._cleanup_errors),
                    "providers": deepcopy(self._provider_stop_status),
                }
            )
            if self._lifecycle_has_active_resources():
                aggregate["active_resources"] = True
                aggregate["private_credentials_destroyed"] = False
            projection["aggregate_secret_audit"] = aggregate
        return projection

    def cleanup_identifiers(self) -> dict[str, Any]:
        with self._cleanup_lock:
            if self._cleanup_snapshot is not None:
                return deepcopy(self._cleanup_snapshot)
            projection = self._build_cleanup_projection()
            return deepcopy(projection)
