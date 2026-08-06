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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from ..contracts import AgentPackage, digest_file
from ..acceptance_runtime import (
    ReportSinkServer,
    ScopedReadProxy,
    _copy_private,
    child_config_digest,
    prepare_child_tree,
)
from ..capability_mcp import ROLE_OPERATIONS
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
)

_DEEPSEEK_API_KEY_ENV = "DEEPSEEK_API_KEY"
_DEEPSEEK_BASE_URL = "https://api.deepseek.com/"
_DEEPSEEK_MODEL = "deepseek-v4-flash"
_DEEPSEEK_PROVIDER = "deepseek"


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
    if api_key is not None:
        values[_DEEPSEEK_API_KEY_ENV] = api_key
    return values


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
    schema_version: int = 1
    proof_gate: bool = False
    fallback_eligible: bool = False
    retrieval_episode: int = 0
    retrieval_state: str = "idle"
    completed_mcp_item_ids: set[str] = field(default_factory=set)
    io_lock: threading.RLock = field(default_factory=threading.RLock)
    state_lock: threading.RLock = field(default_factory=threading.RLock)


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
        self.stopped = False
        self.destroyed = False
        self.failure_category: str | None = None
        self.failure_reason: str | None = None
        self.infrastructure_failure: Any | None = None
        self._failure_recorded = False
        self.startup_complete = startup_complete
        self._watchdog_stop = threading.Event()
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
                    self._record_failure(
                        "runtime",
                        "child-timeout" if self.startup_complete else "child-start-failed",
                    )
                    self._terminate_process(grace_seconds=0.5)
                    return

        threading.Thread(target=watch, name="acceptance-child-watchdog", daemon=True).start()

    def failure_evidence(self) -> dict[str, str] | None:
        """Return only fixed sanitized infrastructure codes for the carrier."""
        if not self.failure_category or not self.failure_reason:
            return None
        return {
            "failure_category": self.failure_category,
            "reason_code": self.failure_reason,
        }

    def _record_failure(self, category: str, reason: str) -> None:
        if self._failure_recorded or self.stopped or self.destroyed:
            return
        self.failure_category = category
        self.failure_reason = reason
        self._failure_recorded = True
        callback = self.spec.get("record_infrastructure_failure")
        if callable(callback):
            try:
                self.infrastructure_failure = callback(category, reason)
            except Exception:
                # The fixed local codes remain available to Acceptance even if a
                # crashing process races carrier teardown; no raw exception text is
                # retained in child evidence.
                self.infrastructure_failure = None

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
        self._watchdog_stop.set()
        self._terminate_process()
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
        self.spec.pop("platform_forwarder", None)
        self.spec.pop("_runtime_proxy", None)
        self.spec.pop("_runtime_report_sink", None)
        self.stopped = True

    def destroy(self) -> None:
        self.stop()
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
        self.root, self.codex_binary, self.use_bwrap, self.process_factory = (
            repository_root,
            codex_binary,
            use_bwrap,
            process_factory,
        )
        self._acceptance_child_factory = acceptance_child_factory
        self._acceptance_children: dict[str, Any] = {}
        self.agents: dict[str, _Agent] = {}
        self._messages: list[RuntimeMessage] = []
        self._run_root: Path | None = None
        self._run_id: str | None = None
        self._acceptance: Any | None = None
        self._coordination_enabled = False
        self._candidate_platform_gate_enabled = False
        self._formal_turn_binding_required = False
        self._private_credentials_destroyed: dict[str, bool] = {}

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

    @staticmethod
    def _child_package_assets(kind: str, root: Path) -> tuple[Path, Path, Path]:
        if kind not in {"source", "platform"}:
            raise CodexRuntimeError("Examiner child kind is invalid")
        package = root / "modeling_team" / "agent-packages" / f"{kind}-examiner"
        instructions = package / "instructions.md"
        skill = (
            root
            / "skills"
            / ("source-examiner" if kind == "source" else "platform-examiner")
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
            if isinstance(private_root, str) and private_root:
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
        if kind not in {"source", "platform"}:
            raise CodexRuntimeError("Examiner child kind is invalid")
        deepseek_enabled = bool(
            self._coordination_enabled
            or spec.get("deepseek_provider") is True
            or spec.get("task_id") == "r2-3-005-formal-acceptance"
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
        _package_file, instructions, skill = self._child_package_assets(kind, self.root)
        paths = prepare_child_tree(
            private_root=private_root,
            host_auth=self.preflight_host_auth(),
            instructions=instructions.read_bytes(),
            skill_name=skill.parent.name,
            skill_bytes=skill.read_bytes(),
        )
        home, work, skills = paths["home"], paths["work"], paths["skills"]
        # Carrier input/source bytes are staged before the adapter is invoked.  Copy only
        # the projected input into the child home; the Platform child never receives the
        # source directory, while the Source child receives exact approved bytes.
        input_path = Path(str(spec["private_input"]))
        if input_path.is_symlink() or not input_path.is_file():
            raise CodexRuntimeError("Examiner projected input is unavailable")
        self._write_child_private(home / "input.json", input_path.read_bytes(), 0o400)
        staged_sources = private_root / "sources"
        if kind == "source" and staged_sources.exists():
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
        report_token = secrets.token_urlsafe(24)
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
        submitted_reports: list[Mapping[str, Any]] = []
        report_submit = spec.get("report_submit")
        report_callback = report_submit if callable(report_submit) else submitted_reports.append
        report_sink = ReportSinkServer(report_socket, report_token, report_callback)
        spec["_runtime_report_sink"] = report_sink
        report_sink.start()
        def _write_private(path: Path, payload: bytes, mode: int) -> None:
            self._write_child_private(path, payload, mode)
        _write_private(report_token_path, report_token.encode("utf-8"), 0o400)
        proxy: ScopedReadProxy | None = None
        proxy_socket: Path | None = None
        proxy_token_path: Path | None = None
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
            proxy_token = secrets.token_urlsafe(24)
            proxy_socket = home / "platform-proxy.sock"
            proxy_token_path = home / "platform-proxy.token"
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
            config_lines.extend(
                [
                    "[mcp_servers.platform_read_proxy]",
                    'command = "/usr/bin/python3"',
                    'args = ["/agent/home/read_proxy_mcp.py", "--stdio", "--socket", "/agent/home/platform-proxy.sock", "--token-file", "/agent/home/platform-proxy.token"]',
                    "required = true",
                    "[mcp_servers.platform_read_proxy.env]",
                    f'PLATFORM_PROXY_PROJECT_ID = {json.dumps(str(spec["platform_read_scope"]["project_id"]))}',
                    f'PLATFORM_PROXY_ONTOLOGY_ID = {json.dumps(str(spec["platform_read_scope"]["ontology_id"]))}',
                    f'PLATFORM_PROXY_GRAPH_SET_ID = {json.dumps(str(spec["platform_read_scope"]["graph_set_id"]))}',
                    f'PLATFORM_PROXY_TICKET_DIGEST = {json.dumps(str(spec["ticket_digest"]))}',
                    f'PLATFORM_PROXY_MODEL_STATE_DIGEST = {json.dumps(str(spec["model_state_digest"]))}',
                ]
            )
        config_lines.extend(
            [
                "[mcp_servers.examiner_report]",
                'command = "/usr/bin/python3"',
                'args = ["/agent/home/report_sink_mcp.py", "--stdio", "--socket", "/agent/home/report.sock", "--token-file", "/agent/home/report-sink.token"]',
                "required = true",
            ]
        )
        if deepseek_enabled:
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
        spec.pop("_runtime_proxy", None)
        spec.pop("_runtime_report_sink", None)
        child_package = AgentPackage(
            package_id=f"{kind}-examiner",
            role="source-specialist",
            description=f"Private {kind} Examiner",
            instructions_path=home / "instructions.md",
            required_skills=(skills / skill.parent.name / "SKILL.md",),
            references=(),
            permissions={"team_transport": False, "platform": "read" if kind == "platform" else "none", "source": "read" if kind == "source" else "none", "spawn": False, "write": False},
            runtime={"codex": {"sandbox": "read-only"}},
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
        try:
            self._rpc(child_agent, "initialize", {"clientInfo": {"name": "modeling-team-examiner", "version": "1"}})
            thread_result = self._rpc(
                child_agent,
                "thread/start",
                {
                    "cwd": "/agent/work",
                    "baseInstructions": "",
                    "developerInstructions": instructions.read_text(encoding="utf-8"),
                    "config": {"web_search": "disabled", "default_tools_enabled": False},
                    "sandbox": "read-only",
                },
            )
            thread = thread_result.get("thread", thread_result) if isinstance(thread_result, dict) else {}
            thread_id = thread.get("id") if isinstance(thread, dict) else None
            if not isinstance(thread_id, str) or not thread_id:
                raise CodexRuntimeError("Examiner thread/start lacked Thread identity")
            # The child must discover the exact local MCP inventory before any model
            # turn.  This makes a missing/extra wrapper a startup contract failure,
            # rather than an ambiguous semantic report.
            child_agent.thread_id = thread_id
            self._require_expected_mcp_servers(child_agent)
            first_turn_input = [
                {
                    "type": "text",
                    "text": (
                        "Read only /agent/home/input.json. Call the MCP tool "
                        "submit_examiner_report exactly once with one bounded terminal "
                        "report. Do not use raw sockets or any other capability."
                    ),
                }
            ]
            turn_result = self._rpc(child_agent, "turn/start", {"threadId": thread_id, "input": first_turn_input})
            resource.thread_id = thread_id
            resource.first_turn_input = first_turn_input
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
    def _is_formal_acceptance_run(run: Any) -> bool:
        configuration = getattr(run, "configuration", None)
        task = getattr(configuration, "task", None)
        profile = getattr(configuration, "profile", None)
        return bool(
            getattr(task, "schema_version", 1) == 2
            and (
                getattr(task, "task_id", None) == "r2-3-005-formal-acceptance"
                or getattr(profile, "profile_id", None) == "r2-3-005-modeling-team"
            )
        )

    @classmethod
    def _candidate_platform_gate_enabled_for_run(cls, run: Any) -> bool:
        configuration = getattr(run, "configuration", None)
        task = getattr(configuration, "task", None)
        return cls._is_formal_acceptance_run(run) and getattr(task, "schema_version", 1) == 2

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
        """Return only capabilities actually configured for this formal run."""

        formal_run = self._coordination_enabled or (
            run is not None and self._is_formal_acceptance_run(run)
        )
        if not formal_run or self._acceptance is None:
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

    def start_roster(self, run: Any, agents: Any) -> list[AgentRuntimeIdentity]:
        self._run_root = run.root
        self._run_id = run.run_id
        self._acceptance = getattr(run, "acceptance", None)
        self._coordination_enabled = self._is_formal_acceptance_run(run)
        self._candidate_platform_gate_enabled = (
            self._coordination_enabled
            and getattr(
                getattr(getattr(run, "configuration", None), "task", None),
                "schema_version",
                1,
            )
            == 2
        )
        self._formal_turn_binding_required = self._coordination_enabled
        if self._coordination_enabled:
            # A missing or insecure provider key is a no-start failure.  Resolve it
            # before creating the first private role tree or invoking process_factory.
            self._resolve_deepseek_api_key()
            self._deepseek_enabled = True
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
                frozenset(run.configuration.task.protocol_tools)
                if package.role == "protocol" and run.configuration.task.schema_version == 2
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
            self._stage_protocol_mechanics_contract(run, agent)
            self._stage_protocol_retrieval_mcp(run, agent)
            self._stage_skills(agent)
            self._write_config(run, agent)
            agent.process = self._start_process(agent)
            self._initialize(agent)
            agent.app_server_host_pid = self._app_server_host_pid(agent)
            identities.append(
                AgentRuntimeIdentity(agent.agent_id, f"codex-thread:{agent.thread_id}")
            )
        return identities

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
        deepseek_enabled = self._is_formal_acceptance_run(run) or self._coordination_enabled
        model_override = _codex_package_model_override(agent.package)
        if deepseek_enabled:
            # Resolve before staging any private artifact.  start_roster also performs
            # this check before entering its first process-launch loop.
            self._resolve_deepseek_api_key()
            self._deepseek_enabled = True
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
        # Only the Protocol receives its platform key/config.  Acceptance never gets
        # platform authentication material or source bytes; formal R2.3-005 Acceptance
        # receives only a private model-provider auth copy for its own Codex process,
        # while its sole model-visible capability remains the Runner-owned local carrier.
        if agent.package.role != "acceptance":
            host_auth = self.preflight_host_auth()
            shutil.copyfile(host_auth, agent.home / "auth.json")
            os.chmod(agent.home / "auth.json", 0o600)
        elif formal_acceptance_auth:
            _copy_private(self.preflight_host_auth(), agent.home / "auth.json", 0o600)
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
        if agent.package.role == "protocol":
            key = run.protocol_key
            if not key:
                raise CodexRuntimeError(
                    "Protocol key is required before Runtime startup"
                )
            platform = agent.home / "platform"
            shutil.copytree(self.root / "backend" / "app", platform / "app")
            formal_candidate_gate = self._candidate_platform_gate_enabled_for_run(run)
            if formal_candidate_gate:
                CandidatePlatformGate.ensure(run.root / "candidate-gate")
            lines.extend(
                protocol_mcp_launch_spec(
                    agent.platform_tools,
                    schema_version=getattr(task, "schema_version", 1),
                    candidate_gate_path=(
                        CANDIDATE_PLATFORM_GATE_MOUNT if formal_candidate_gate else None
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
            token_target.write_text(token_source.read_text(encoding="utf-8"), encoding="utf-8")
            os.chmod(token_target, 0o400)
            lines.extend(
                [
                    "[mcp_servers.runner_capability]",
                    'command = "/usr/bin/python3"',
                    'args = ["/agent/home/runner_capability_mcp.py", "--stdio", "--socket", "/agent/home/runner-capability.sock", "--token-file", "/agent/home/runner-capability.token"]',
                    "required = true",
                ]
            )
        if model_override is not None:
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
                list(ROLE_OPERATIONS.get(agent.package.role, ()))
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
            self._coordination_enabled
            and self._acceptance is not None
            and self._role_capability_operations(agent.package.role)
        ):
            command[command.index("--chdir") : command.index("--chdir")] = [
                "--bind",
                str(self._acceptance.capability_socket_path(agent.package.role)),
                "/agent/home/runner-capability.sock",
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
            resolved_python = (self.root / "backend" / ".venv" / "bin" / "python").resolve()
            runtime_root = resolved_python.parent.parent
            runtime_dirs: list[str] = []
            current = Path("/")
            for part in runtime_root.parent.parts[1:]:
                current /= part
                runtime_dirs.extend(["--dir", str(current)])
            command[command.index("--chdir") : command.index("--chdir")] = [
                "--dir",
                "/backend",
                "--ro-bind",
                str(self.root / "backend" / "app"),
                "/backend/app",
                "--ro-bind",
                str(self.root / "backend" / ".venv"),
                "/backend/.venv",
                *runtime_dirs,
                "--ro-bind",
                str(runtime_root),
                str(runtime_root),
            ]
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
        command[command.index("--chdir") : command.index("--chdir")] = [
            "--dir",
            "/agent/bin",
            "--ro-bind",
            binary,
            "/agent/bin/codex",
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
        model_override = _codex_package_model_override(agent.package)
        api_key = (
            self._resolve_deepseek_api_key()
            if (self._coordination_enabled or getattr(self, "_deepseek_enabled", False))
            and model_override is None
            else None
        )
        command = self.namespace_command(agent)
        descriptors = agent.retrieval_asset_fds
        try:
            return self.process_factory(
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

    def _rpc_locked(
        self, agent: _Agent, method: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        if (
            agent.process is None
            or agent.process.stdin is None
            or agent.process.stdout is None
        ):
            raise CodexRuntimeError("app-server is unavailable")
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
            if value.get("id") == request_id:
                if "error" in value:
                    raise CodexRuntimeError(
                        f"app-server {method} failed: {value['error']}"
                    )
                return value.get("result", {})
            self._notification(agent, value)
        raise CodexRuntimeError(f"app-server did not answer {method}")

    def _drain_agent_output_locked(self, agent: _Agent) -> None:
        """Apply every App Server notification already readable while holding its I/O lock."""
        if agent.process is None or agent.process.stdout is None:
            return
        while True:
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
        result = self._rpc(
            agent,
            "thread/start",
            {
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
                "sandbox": agent.package.runtime["codex"]["sandbox"],
            },
        )
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
                    "verify_scoped_retrieval_fallback",
                }
                if self._coordination_enabled:
                    expected["protocol_mechanics"].add("build_candidate_conflict")
                if agent.proof_gate:
                    expected["protocol_mechanics"].add("write_candidate_item_evidence_map")
        capability_operations = self._role_capability_operations(agent.package.role)
        if capability_operations:
            expected["runner_capability"] = set(capability_operations)
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
                str(name)
                for name, tool in raw_tools.items()
                if isinstance(tool, dict)
                and isinstance(tool.get("name"), str)
                and tool["name"] == name
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
        agent.active_turn_id = self._turn_id(result)
        agent.state = "running"

    @staticmethod
    def _turn_id(result: dict[str, Any]) -> str | None:
        turn = result.get("turn", result)
        return (
            turn.get("id")
            if isinstance(turn, dict) and isinstance(turn.get("id"), str)
            else None
        )

    @staticmethod
    def _expected_active_turn_id(error: str) -> str | None:
        match = re.search(r"found `([^`]+)`", error)
        return match.group(1) if match else None

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
                if "no active turn to steer" in str(exc):
                    agent.active_turn_id, agent.state = None, "idle"
                else:
                    active = self._expected_active_turn_id(str(exc))
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
        return RuntimeDispatchReceipt("start", agent.active_turn_id)

    def _notification(self, agent: _Agent, value: dict[str, Any]) -> None:
        method, params = value.get("method"), value.get("params", {})
        if isinstance(method, str):
            self._append_runtime_evidence(
                "app-server-events",
                {
                    "agent_id": agent.agent_id,
                    "method": method,
                    "has_request_id": "id" in value,
                    "param_keys": sorted(params) if isinstance(params, dict) else [],
                    **(
                        {"action": "decline", "decision": "decline"}
                        if method == "item/commandExecution/requestApproval" and "id" in value
                        else {}
                    ),
                },
            )
        if method == "item/commandExecution/requestApproval" and "id" in value:
            self._append_runtime_evidence(
                "command-approval-events",
                {
                    "agent_id": agent.agent_id,
                    "method": method,
                    "decision": "decline",
                    "param_keys": sorted(params) if isinstance(params, dict) else [],
                },
            )
            self._respond_server_request(agent, value["id"], {"decision": "decline"})
            return
        if method == "item/tool/call" and "id" in value and isinstance(params, dict):
            self._respond_dynamic_tool(agent, value["id"], params)
            return
        if (
            method == "mcpServer/elicitation/request"
            and "id" in value
            and isinstance(params, dict)
        ):
            # App Server routes MCP tool approval through elicitation. Accept only the preflight-
            # locked Profile servers plus the v2 Protocol-only native verifier; all other requests
            # fail closed.
            schema = params.get("requestedSchema")
            server_name = str(params.get("serverName", ""))
            expected = server_name == "team_transport" or (
                agent.package.role == "protocol" and server_name == "ontology_platform"
            ) or (
                agent.package.role == "protocol"
                and agent.schema_version == 2
                and server_name == "protocol_mechanics"
            ) or (
                bool(self._role_capability_operations(agent.package.role))
                and server_name == "runner_capability"
            )
            action = "accept" if expected else "decline"
            self._append_runtime_evidence(
                "mcp-elicitations",
                {
                    "agent_id": agent.agent_id,
                    "server_name": server_name,
                    "mode": str(params.get("mode", "")),
                    "schema_keys": sorted(schema) if isinstance(schema, dict) else [],
                    "action": action,
                },
            )
            self._respond_server_request(agent, value["id"], {"action": action, "content": {}})
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
                if isinstance(turn, dict) and isinstance(turn.get("id"), str):
                    agent.active_turn_id, agent.last_started_turn_id, agent.state = (
                        turn["id"],
                        turn["id"],
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
        for agent in self.agents.values():
            with agent.io_lock:
                self._drain_agent_output_locked(agent)
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

    def stop(self) -> None:
        # Temporary Examiner resources are Runner-owned and must be stopped before
        # persistent Agent shutdown.  This path is idempotent and uses only the
        # injected resource seam; it does not create or discover arbitrary children.
        for handle_digest, resource in list(self._acceptance_children.items()):
            try:
                stop = getattr(resource, "stop", None)
                if callable(stop):
                    stop()
                destroy = getattr(resource, "destroy", None)
                if callable(destroy):
                    destroy()
            finally:
                self._acceptance_children.pop(handle_digest, None)
        for agent in self.agents.values():
            self._close_retrieval_asset_fds(agent)
            if agent.process and agent.process.poll() is None:
                try:
                    os.killpg(os.getpgid(agent.process.pid), signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    agent.process.terminate()
                try:
                    agent.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(os.getpgid(agent.process.pid), signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        agent.process.kill()
                    agent.process.wait(timeout=5)
            artifact_names = _PRIVATE_AGENT_BASE_ARTIFACT_NAMES
            if self._coordination_enabled:
                artifact_names += _PRIVATE_FORMAL_AGENT_ARTIFACT_NAMES
            cleanup_ok = True
            for name in artifact_names:
                credential = agent.home / name
                try:
                    credential.unlink(missing_ok=True)
                except OSError:
                    cleanup_ok = False
            residual = any(
                (agent.home / name).exists() or (agent.home / name).is_symlink()
                for name in artifact_names
            )
            self._private_credentials_destroyed[agent.agent_id] = cleanup_ok and not residual
            agent.state = "stopped"

    def cleanup_identifiers(self) -> dict[str, Any]:
        identifiers = {}
        artifact_names = _PRIVATE_AGENT_BASE_ARTIFACT_NAMES
        if self._coordination_enabled:
            artifact_names += _PRIVATE_FORMAL_AGENT_ARTIFACT_NAMES
        for key, value in self.agents.items():
            private_credentials_destroyed = self._private_credentials_destroyed.get(key, False)
            if private_credentials_destroyed:
                private_credentials_destroyed = not any(
                    (value.home / name).exists() or (value.home / name).is_symlink()
                    for name in artifact_names
                )
            identifiers[key] = {
                "thread_id": value.thread_id,
                "pid": value.process.pid if value.process else None,
                "private_credentials_destroyed": private_credentials_destroyed,
            }
        return identifiers | {
            "acceptance_children": {
                "active": len(self._acceptance_children),
                "zero_residue": not self._acceptance_children,
            }
        }
