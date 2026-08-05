"""Private runtime helpers for the R2.3-005 Examiner children.

The Runner owns this module.  It deliberately has no semantic authority: the platform
proxy validates a frozen ticket envelope before forwarding to the host-owned canonical
MCP server.  ``ScopedReadProxy`` can still be constructed without a forwarder by
explicit deterministic offline tests; formal Runner children always bind the concrete
``McpReadForwarder`` created by the platform read-key lifecycle.
"""

from __future__ import annotations

import hashlib
import asyncio
import json
import os
import queue
import socket
import stat
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping


class ChildRuntimeError(RuntimeError):
    """A private child/proxy contract failed closed."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _safe_digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ChildRuntimeError(f"{field} is invalid")
    return value


def _safe_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in value):
        raise ChildRuntimeError(f"{field} is invalid")
    return value


def _private_dir(path: Path, *, create: bool = False) -> None:
    if create:
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
    try:
        metadata = os.lstat(path)
    except OSError as exc:
        raise ChildRuntimeError("private runtime directory is unavailable") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or metadata.st_uid != os.getuid()
    ):
        raise ChildRuntimeError("private runtime directory is not 0700")


def _write_private(path: Path, payload: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if path.is_symlink() or path.exists():
        raise ChildRuntimeError("private runtime artifact already exists")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _copy_private(source: Path, target: Path, mode: int) -> None:
    """Copy one trusted regular file into a private tree without following links."""
    try:
        metadata = os.lstat(source)
    except OSError as exc:
        raise ChildRuntimeError("private source is unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ChildRuntimeError("private source is invalid")
    _private_dir(target.parent)
    descriptor = -1
    try:
        descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
        metadata = os.fstat(descriptor)
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise ChildRuntimeError("private source is invalid")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            payload = stream.read()
    except OSError as exc:
        raise ChildRuntimeError("private source is unavailable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    _write_private(target, payload, mode)


PLATFORM_PROXY_READ_TOOLS: tuple[str, ...] = (
    "check_platform_health",
    "get_project_build_context",
    "get_build_session",
    "get_modeling_context",
    "get_ontology_workspace_context",
    "get_ontology_read_model",
    "get_semantic_read_model",
    "query_semantic_context",
    "semantic_sparql_query",
    "describe_semantic_graph_set",
    "list_semantic_derived_pointers",
    "inspect_semantic_projection_status",
    "list_evidence_references",
    "get_evidence_reference",
    "get_ontology_lineage",
    "inspect_semantic_statement_provenance",
    "get_semantic_reasoning_run",
    "get_semantic_validation_run",
    "list_semantic_reasoning_runs",
    "list_semantic_validation_runs",
)


@dataclass(frozen=True)
class ProxyReceipt:
    # This is a child-visible virtual identity, never the host AF_UNIX path.  Host paths
    # are runtime-only and must not enter child-config or durable cleanup evidence.
    socket_identity: str
    token_digest: str
    project_id: str
    ontology_id: str
    graph_set_id: str
    ticket_digest: str
    allowed_tools: tuple[str, ...]
    config_digest: str


@dataclass(frozen=True)
class ProxyCallReceipt:
    """Sanitized receipt for one successful scoped read.

    The receipt intentionally contains no key, token, raw response, socket path, or
    host filesystem location.  ``artifact_path`` is a Runner-relative retained
    evidence name and is safe for the child to echo in its typed report reference.
    """

    ordinal: int
    project_id: str
    ontology_id: str
    graph_set_id: str
    ticket_digest: str
    model_state_digest: str
    tool: str
    request_digest: str
    response_digest: str
    artifact_path: str


class ScopedReadProxy:
    """A Runner-owned, ticket-bound AF_UNIX read proxy.

    ``read_key`` is intentionally retained only in this object.  It is never written to
    the child home, environment, config, receipt, or proxy response.  The optional
    ``forward`` callback is the only place an integration may attach a real platform
    read; leaving it unset gives deterministic tests a safe offline proxy.
    """

    def __init__(
        self,
        *,
        socket_path: Path,
        token: str,
        read_key: str,
        project_id: str,
        ontology_id: str,
        graph_set_id: str,
        ticket_digest: str,
        model_state_digest: str,
        allowed_tools: list[str] | tuple[str, ...],
        forward: Callable[[str, Mapping[str, Any], str], Mapping[str, Any]] | None = None,
        acceptance_round_id: str | None = None,
        child_handle_digest: str | None = None,
    ) -> None:
        self.socket_path = socket_path
        self.token = token
        self._read_key: str | None = read_key
        self.project_id = _safe_id(project_id, "project_id")
        self.ontology_id = _safe_id(ontology_id, "ontology_id")
        self.graph_set_id = _safe_id(graph_set_id, "graph_set_id")
        self.ticket_digest = _safe_digest(ticket_digest, "ticket_digest")
        self.model_state_digest = _safe_digest(model_state_digest, "model_state_digest")
        normalized = tuple(str(tool) for tool in allowed_tools)
        if (
            not normalized
            or len(set(normalized)) != len(normalized)
            or any(tool not in PLATFORM_PROXY_READ_TOOLS for tool in normalized)
        ):
            raise ChildRuntimeError("platform proxy allowlist is not read-only")
        required_wrappers = {
            "list_semantic_validation_runs",
            "get_semantic_validation_run",
            "list_semantic_reasoning_runs",
            "get_semantic_reasoning_run",
        }
        if not required_wrappers.issubset(normalized):
            raise ChildRuntimeError("platform proxy allowlist omits validation/reasoning readers")
        self.allowed_tools = normalized
        self._forward = forward
        self.acceptance_round_id = (
            _safe_id(acceptance_round_id, "acceptance_round_id")
            if acceptance_round_id is not None
            else "offline-round"
        )
        self.child_handle_digest = (
            _safe_digest(child_handle_digest, "child_handle_digest")
            if child_handle_digest is not None
            else "0" * 64
        )
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self.requests: list[dict[str, Any]] = []
        self._call_receipts: list[ProxyCallReceipt] = []
        self.post_revoke_denials = 0

    @property
    def active(self) -> bool:
        with self._lock:
            return self._read_key is not None

    @property
    def token_digest(self) -> str:
        return hashlib.sha256(self.token.encode("utf-8")).hexdigest()

    @property
    def receipt(self) -> ProxyReceipt:
        config = {
            "server": "platform_read_proxy",
            "scope": {
                "project_id": self.project_id,
                "ontology_id": self.ontology_id,
                "graph_set_id": self.graph_set_id,
            },
            "ticket_digest": self.ticket_digest,
            "model_state_digest": self.model_state_digest,
            "allowed_tools": list(self.allowed_tools),
        }
        return ProxyReceipt(
            socket_identity="/agent/home/platform-proxy.sock",
            token_digest=self.token_digest,
            project_id=self.project_id,
            ontology_id=self.ontology_id,
            graph_set_id=self.graph_set_id,
            ticket_digest=self.ticket_digest,
            allowed_tools=self.allowed_tools,
            config_digest=_digest(config),
        )

    @property
    def receipt_snapshot(self) -> tuple[ProxyCallReceipt, ...]:
        """Return immutable sanitized receipts for successful calls only."""

        with self._lock:
            return tuple(self._call_receipts)

    def start(self) -> ProxyReceipt:
        with self._lock:
            if self._server is not None:
                return self.receipt
            self.socket_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            if self.socket_path.exists() or self.socket_path.is_symlink():
                raise ChildRuntimeError("platform proxy socket already exists")
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                server.bind(str(self.socket_path))
                os.chmod(self.socket_path, 0o600)
                server.listen(8)
            except Exception:
                server.close()
                self.socket_path.unlink(missing_ok=True)
                raise
            self._server = server
            self._stop.clear()
            self._thread = threading.Thread(target=self._serve, name="acceptance-read-proxy", daemon=True)
            self._thread.start()
            return self.receipt

    def _serve(self) -> None:
        server = self._server
        if server is None:
            return
        server.settimeout(0.2)
        while not self._stop.is_set():
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with conn:
                conn.settimeout(2.0)
                try:
                    raw = b""
                    while b"\n" not in raw and len(raw) < 128 * 1024:
                        block = conn.recv(8192)
                        if not block:
                            break
                        raw += block
                    request = json.loads(raw.split(b"\n", 1)[0].decode("utf-8")) if raw else {}
                    response = self.handle(request)
                except Exception as exc:
                    response = {"ok": False, "error": "proxy-request-invalid", "code": type(exc).__name__}
                try:
                    conn.sendall(_canonical(response) + b"\n")
                except OSError:
                    pass

    def handle(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(request, Mapping):
            raise ChildRuntimeError("proxy request is invalid")
        with self._lock:
            if self._read_key is None:
                self.post_revoke_denials += 1
                return {"ok": False, "error": "read-key-revoked", "code": "read-key-revoked"}
            if request.get("token") != self.token:
                return {"ok": False, "error": "proxy-token-invalid", "code": "proxy-token-invalid"}
            operation = request.get("operation")
            if operation == "tools/list":
                return {"ok": True, "tools": list(self.allowed_tools)}
            if operation != "tools/call":
                return {"ok": False, "error": "proxy-operation-denied", "code": "proxy-operation-denied"}
            tool = request.get("tool")
            arguments = request.get("arguments")
            if not isinstance(tool, str) or tool not in self.allowed_tools:
                return {"ok": False, "error": "read-tool-denied", "code": "read-tool-denied"}
            if not isinstance(arguments, Mapping):
                return {"ok": False, "error": "read-arguments-invalid", "code": "read-arguments-invalid"}
            required = {
                "project_id": self.project_id,
                "ontology_id": self.ontology_id,
                "graph_set_id": self.graph_set_id,
                "ticket_digest": self.ticket_digest,
                "model_state_digest": self.model_state_digest,
            }
            if any(arguments.get(key) != value for key, value in required.items()):
                return {"ok": False, "error": "read-scope-denied", "code": "read-scope-denied"}
            request_digest = _digest({"tool": tool, "arguments": dict(arguments)})
            self.requests.append({"tool": tool, "request_digest": request_digest})
            if self._forward is None:
                return {"ok": False, "error": "platform-forwarding-unconfigured", "code": "platform-forwarding-unconfigured"}
            try:
                result = dict(self._forward(tool, arguments, self._read_key))
            except Exception:
                return {"ok": False, "error": "platform-forward-failed", "code": "platform-forward-failed"}
            response_digest = _digest(result)
            artifact_path = (
                f"acceptance/{self.acceptance_round_id}/platform-read/"
                f"{self.child_handle_digest}/{len(self._call_receipts)}.json"
            )
            self._call_receipts.append(
                ProxyCallReceipt(
                    ordinal=len(self._call_receipts),
                    project_id=self.project_id,
                    ontology_id=self.ontology_id,
                    graph_set_id=self.graph_set_id,
                    ticket_digest=self.ticket_digest,
                    model_state_digest=self.model_state_digest,
                    tool=tool,
                    request_digest=request_digest,
                    response_digest=response_digest,
                    artifact_path=artifact_path,
                )
            )
            return {
                "ok": True,
                "result": result,
                "request_digest": request_digest,
                "response_digest": response_digest,
                "artifact_path": artifact_path,
            }

    def revoke(self) -> dict[str, Any]:
        with self._lock:
            self._read_key = None
            return {"status": "revoked", "post_revoke_denials": self.post_revoke_denials}

    def stop(self) -> None:
        self._stop.set()
        server = self._server
        self._server = None
        if server is not None:
            try:
                server.close()
            finally:
                self.socket_path.unlink(missing_ok=True)
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=1)

    def destroy(self) -> None:
        self.revoke()
        self.stop()


@dataclass
class _ForwardRequest:
    tool: str
    arguments: Mapping[str, Any]
    result: Any = None
    error: BaseException | None = None
    complete: threading.Event = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.complete = threading.Event()


class McpReadForwarder:
    """Host-side synchronous facade over the canonical backend MCP server.

    The forwarder owns the only subprocess environment containing the temporary read
    key.  Its environment is allowlisted and its child-facing API is restricted to the
    ticket's read tools.  Calls are serialized through one MCP ``ClientSession`` so
    pagination cursors and result envelopes remain byte-for-byte typed values rather
    than being reimplemented by the Runner.
    """

    _SCOPED_ENVELOPE_FIELDS = frozenset(
        {"ticket_digest", "model_state_digest"}
    )

    def __init__(
        self,
        *,
        repository_root: Path,
        read_key: str,
        expected_tools: list[str] | tuple[str, ...],
        command: str | None = None,
        args: list[str] | None = None,
        process_env: Mapping[str, str] | None = None,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        if not isinstance(read_key, str) or not read_key:
            raise ChildRuntimeError("forwarder read key is unavailable")
        normalized = tuple(str(tool) for tool in expected_tools)
        if not normalized or len(set(normalized)) != len(normalized):
            raise ChildRuntimeError("forwarder tool inventory is invalid")
        if any(tool not in PLATFORM_PROXY_READ_TOOLS for tool in normalized):
            raise ChildRuntimeError("forwarder tool inventory is not read-only")
        self.repository_root = repository_root.resolve()
        self.read_key = read_key
        self.expected_tools = normalized
        self.command = command or str(self.repository_root / "backend" / ".venv" / "bin" / "python")
        self.args = list(args or ["-m", "app.mcp.server"])
        backend_root = self.repository_root / "backend"
        # Never inherit the caller's environment wholesale: especially do not leak a
        # broader API key, proxy, plugin, or Codex credential into the canonical server.
        allowlisted = {
            "ONTOLOGY_MCP_API_KEY": read_key,
            "PYTHONPATH": str(backend_root),
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(backend_root),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }
        if process_env:
            for name in ("DATABASE_URL", "OXIGRAPH_URL", "EMBEDDING_BASE_URL", "EMBEDDING_MODEL"):
                value = process_env.get(name)
                if isinstance(value, str) and value:
                    allowlisted[name] = value
        self.process_env = allowlisted
        self.client_factory = client_factory
        self._queue: queue.Queue[_ForwardRequest | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._stopped = threading.Event()
        self._startup_error: BaseException | None = None
        self._tool_schemas: dict[str, Mapping[str, Any]] = {}
        self._inventory_digest: str | None = None

    @property
    def inventory_digest(self) -> str | None:
        return self._inventory_digest

    @property
    def active(self) -> bool:
        return self._thread is not None and not self._stopped.is_set()

    def start(self, *, timeout: float = 20.0) -> "McpReadForwarder":
        if self._thread is not None:
            if self._startup_error is not None:
                raise ChildRuntimeError("canonical MCP forwarder failed to start") from self._startup_error
            return self
        self._stopped.clear()
        self._thread = threading.Thread(target=self._run, name="acceptance-mcp-forwarder", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=max(0.1, timeout)):
            self.stop()
            raise ChildRuntimeError("canonical MCP forwarder startup timed out")
        if self._startup_error is not None:
            error = self._startup_error
            self.stop()
            raise ChildRuntimeError("canonical MCP forwarder startup failed") from error
        return self

    def _run(self) -> None:
        try:
            asyncio.run(self._session_loop())
        except BaseException as exc:  # surfaced to start()/forward() without leaking text
            self._startup_error = exc
            self._ready.set()
            while True:
                request = self._queue.get()
                if request is None:
                    return
                request.error = ChildRuntimeError("canonical MCP forwarder is unavailable")
                request.complete.set()

    async def _session_loop(self) -> None:
        # Imports are deferred so deterministic offline tests do not need to start the
        # backend or initialize its dependency graph.
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        parameters = StdioServerParameters(
            command=self.command,
            args=self.args,
            env=dict(self.process_env),
            cwd=str(self.repository_root / "backend"),
        )
        factory = self.client_factory or stdio_client
        async with factory(parameters) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                listed = await session.list_tools()
                tools = getattr(listed, "tools", ())
                inventory: dict[str, Mapping[str, Any]] = {}
                for tool in tools if isinstance(tools, (list, tuple)) else ():
                    name = getattr(tool, "name", None)
                    if isinstance(name, str):
                        schema = getattr(tool, "inputSchema", None)
                        inventory[name] = schema if isinstance(schema, Mapping) else {}
                # The canonical server may expose additional write tools.  We require
                # every frozen read wrapper to exist and expose only the exact ticket
                # inventory through this proxy; no extra tool can cross the boundary.
                missing = set(self.expected_tools) - set(inventory)
                if missing:
                    raise ChildRuntimeError("canonical MCP read tool inventory is incomplete")
                self._tool_schemas = {name: inventory[name] for name in self.expected_tools}
                self._inventory_digest = _digest(
                    {"canonical_tools": sorted(inventory), "ticket_tools": list(self.expected_tools)}
                )
                self._ready.set()
                while not self._stopped.is_set():
                    request = await asyncio.to_thread(self._queue.get)
                    if request is None:
                        return
                    try:
                        schema = self._tool_schemas.get(request.tool)
                        if schema is None:
                            raise ChildRuntimeError("forwarder tool is outside ticket inventory")
                        properties = schema.get("properties") if isinstance(schema, Mapping) else None
                        arguments = dict(request.arguments)
                        if isinstance(properties, Mapping):
                            arguments = {
                                key: value for key, value in arguments.items() if key in properties
                            }
                        result = await session.call_tool(request.tool, arguments)
                        request.result = self._decode_result(result)
                    except BaseException as exc:
                        request.error = exc
                    finally:
                        request.complete.set()

    @staticmethod
    def _decode_result(result: Any) -> Mapping[str, Any]:
        if bool(getattr(result, "isError", False)):
            raise ChildRuntimeError("canonical MCP read tool returned an error")
        structured = getattr(result, "structuredContent", None)
        if isinstance(structured, Mapping):
            return dict(structured)
        content = getattr(result, "content", ())
        for item in content if isinstance(content, (list, tuple)) else ():
            text = getattr(item, "text", None)
            if not isinstance(text, str):
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(value, Mapping):
                return dict(value)
            return {"value": value}
        raise ChildRuntimeError("canonical MCP read tool returned no typed data")

    def forward(self, tool: str, arguments: Mapping[str, Any], read_key: str) -> Mapping[str, Any]:
        if read_key != self.read_key or not self.active:
            raise ChildRuntimeError("forwarder read key is unavailable")
        request = _ForwardRequest(tool=tool, arguments=dict(arguments))
        self._queue.put(request)
        if not request.complete.wait(timeout=30):
            raise ChildRuntimeError("canonical MCP read tool timed out")
        if request.error is not None:
            raise ChildRuntimeError("canonical MCP read tool failed") from request.error
        if not isinstance(request.result, Mapping):
            raise ChildRuntimeError("canonical MCP read result is not typed")
        return dict(request.result)

    def stop(self) -> None:
        self._stopped.set()
        if self._thread is not None:
            self._queue.put(None)
            self._thread.join(timeout=2)
        self._thread = None
        self.read_key = ""
        self.process_env.pop("ONTOLOGY_MCP_API_KEY", None)


class ReportSinkServer:
    """Write-only private child report endpoint; never Team Transport."""

    def __init__(self, socket_path: Path, token: str, submit: Callable[[Mapping[str, Any]], Any]):
        self.socket_path = socket_path
        self.token = token
        self._submit = submit
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._submitted = False

    def start(self) -> None:
        self.socket_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        if self.socket_path.exists() or self.socket_path.is_symlink():
            raise ChildRuntimeError("report sink socket already exists")
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(str(self.socket_path))
            os.chmod(self.socket_path, 0o600)
            server.listen(2)
        except Exception:
            server.close()
            self.socket_path.unlink(missing_ok=True)
            raise
        server.settimeout(0.2)
        self._server = server
        self._thread = threading.Thread(target=self._serve, name="acceptance-report-sink", daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        server = self._server
        if server is None:
            return
        while not self._stop.is_set():
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with conn:
                try:
                    data = conn.recv(128 * 1024)
                    request = json.loads(data.decode("utf-8")) if data else {}
                    if request.get("token") != self.token:
                        response = {"ok": False, "code": "report-token-invalid"}
                    elif self._submitted:
                        response = {"ok": False, "code": "report-already-submitted"}
                    elif not isinstance(request.get("report"), Mapping):
                        response = {"ok": False, "code": "report-invalid"}
                    else:
                        self._submit(request["report"])
                        self._submitted = True
                        response = {"ok": True}
                    conn.sendall(_canonical(response))
                except Exception:
                    try:
                        conn.sendall(_canonical({"ok": False, "code": "report-rejected"}))
                    except OSError:
                        pass

    def stop(self) -> None:
        self._stop.set()
        server = self._server
        self._server = None
        if server is not None:
            server.close()
        self.socket_path.unlink(missing_ok=True)
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=1)


def child_config_digest(config: Mapping[str, Any]) -> str:
    """Compute a public config binding without retaining secrets."""
    return _digest(config)


def prepare_child_tree(
    *,
    private_root: Path,
    source_bytes: Mapping[str, bytes] | None = None,
    host_auth: Path | None = None,
    instructions: bytes = b"",
    skill_name: str,
    skill_bytes: bytes,
) -> dict[str, Path]:
    """Create the private child home/work/skills tree with strict modes."""
    _private_dir(private_root)
    home, work, skills = private_root / "home", private_root / "work", private_root / "skills"
    for path in (home, work, skills):
        _private_dir(path, create=True)
    if host_auth is not None:
        _copy_private(host_auth, home / "auth.json", 0o600)
    _write_private(home / "instructions.md", instructions, 0o400)
    skill_dir = skills / skill_name
    _private_dir(skill_dir, create=True)
    _write_private(skill_dir / "SKILL.md", skill_bytes, 0o444)
    if source_bytes:
        for relative, payload in source_bytes.items():
            target = home / "sources" / relative
            if Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise ChildRuntimeError("source path escapes child home")
            _write_private(target, payload, 0o400)
    return {"home": home, "work": work, "skills": skills}


__all__ = [
    "ChildRuntimeError",
    "PLATFORM_PROXY_READ_TOOLS",
    "ProxyReceipt",
    "ScopedReadProxy",
    "McpReadForwarder",
    "ReportSinkServer",
    "child_config_digest",
    "prepare_child_tree",
]
