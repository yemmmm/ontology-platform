"""Runner-owned DeepSeek credential binding and loopback Responses proxy.

The formal Team never gives a provider credential to a Codex process.  This module
keeps the only copy in a mutable byte buffer owned by one short-lived loopback
proxy, and validates the external file again immediately before reading it.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import ssl
import stat
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit


DEEPSEEK_API_KEY_ENV = "DEEPSEEK_API_KEY"
DEEPSEEK_CREDENTIAL_PATH = Path(
    "~/.config/ontology-platform/modeling-team-deepseek.env"
).expanduser()
DEEPSEEK_UPSTREAM_URL = "https://api.deepseek.com/responses"
DEEPSEEK_PROXY_MAX_BODY_BYTES = 32 * 1024 * 1024
_CREDENTIAL_MAX_BYTES = 4096
_CREDENTIAL_RE = re.compile(r"DEEPSEEK_API_KEY=([^\s\"'\r\n=]+)\n?\Z")


class DeepSeekCredentialError(RuntimeError):
    """Typed, provider-text-free credential validation failure."""


class DeepSeekProviderProxyError(RuntimeError):
    """Typed loopback proxy startup/transport failure."""


@dataclass(frozen=True)
class DeepSeekCredentialBinding:
    """Non-secret file identity frozen during Runner.prepare."""

    path: Path
    st_dev: int
    st_ino: int
    st_size: int
    st_mtime_ns: int

    @property
    def canonical_path(self) -> str:
        return str(self.path)

    def metadata_matches(self, metadata: os.stat_result) -> bool:
        return (
            stat.S_ISREG(metadata.st_mode)
            and metadata.st_uid == os.getuid()
            and stat.S_IMODE(metadata.st_mode) == 0o600
            and metadata.st_dev == self.st_dev
            and metadata.st_ino == self.st_ino
            and metadata.st_size == self.st_size
            and metadata.st_mtime_ns == self.st_mtime_ns
        )


def _canonical_credential_path(path: Path | str | None) -> Path:
    value = Path(path) if path is not None else DEEPSEEK_CREDENTIAL_PATH
    try:
        expanded = value.expanduser().absolute()
        # Inspect the caller-supplied final path before resolving it.  Resolving
        # first would turn a forbidden symlink into its regular target and defeat
        # the no-follow contract.
        try:
            metadata = os.lstat(expanded)
        except FileNotFoundError:
            metadata = None
        if metadata is not None and stat.S_ISLNK(metadata.st_mode):
            raise DeepSeekCredentialError("DeepSeek credential file is insecure")
        return expanded.resolve(strict=False)
    except DeepSeekCredentialError:
        raise
    except (OSError, RuntimeError) as exc:
        raise DeepSeekCredentialError("DeepSeek credential path is invalid") from exc


def _validate_credential_bytes(payload: bytes) -> bytes:
    if not payload or len(payload) > _CREDENTIAL_MAX_BYTES:
        raise DeepSeekCredentialError("DeepSeek credential file is malformed")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DeepSeekCredentialError("DeepSeek credential file is malformed") from exc
    match = _CREDENTIAL_RE.fullmatch(text)
    if match is None:
        raise DeepSeekCredentialError("DeepSeek credential assignment is malformed")
    value = match.group(1)
    if not value or value.strip() != value:
        raise DeepSeekCredentialError("DeepSeek credential assignment is malformed")
    return value.encode("utf-8")


def preflight_deepseek_credential(path: Path | str | None = None) -> DeepSeekCredentialBinding:
    """Validate the fixed external file and return only non-secret metadata."""

    canonical = _canonical_credential_path(path)
    try:
        metadata = os.lstat(canonical)
    except OSError as exc:
        raise DeepSeekCredentialError("DeepSeek credential file is unavailable") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise DeepSeekCredentialError("DeepSeek credential file is insecure")
    try:
        payload = canonical.read_bytes()
    except OSError as exc:
        raise DeepSeekCredentialError("DeepSeek credential file is unreadable") from exc
    # Validate now but deliberately discard the value.  TeamRun/baseline/evidence
    # receives only this identity, never credential bytes or a digest.
    _validate_credential_bytes(payload)
    return DeepSeekCredentialBinding(
        canonical,
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
    )


def read_deepseek_credential(binding: DeepSeekCredentialBinding) -> bytes:
    """Open with O_NOFOLLOW and revalidate the prepare-time identity."""

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(binding.path, flags)
    except OSError as exc:
        raise DeepSeekCredentialError("DeepSeek credential open failed") from exc
    try:
        metadata = os.fstat(descriptor)
        if not binding.metadata_matches(metadata):
            raise DeepSeekCredentialError("DeepSeek credential binding changed")
        payload = os.read(descriptor, _CREDENTIAL_MAX_BYTES + 1)
        if len(payload) > _CREDENTIAL_MAX_BYTES:
            raise DeepSeekCredentialError("DeepSeek credential file is malformed")
    except OSError as exc:
        raise DeepSeekCredentialError("DeepSeek credential read failed") from exc
    finally:
        os.close(descriptor)
    return _validate_credential_bytes(payload)


class _ProxyHandler(BaseHTTPRequestHandler):
    server_version = "ontology-platform-proxy"
    sys_version = ""

    def log_message(self, _format: str, *_args: object) -> None:
        # Never emit request paths, headers, provider errors, or body content.
        return

    @property
    def proxy(self) -> "DeepSeekProviderProxy":
        return self.server.proxy  # type: ignore[attr-defined,no-any-return]

    def _reject(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Connection", "close")
        self.send_header("Content-Length", "0")
        self.end_headers()
        self.close_connection = True

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler hook
        proxy = self.proxy
        if self.path != "/responses":
            proxy._count("rejected")
            self._reject(404)
            return
        raw_length = self.headers.get("Content-Length")
        try:
            body_length = int(raw_length) if raw_length is not None else -1
        except (TypeError, ValueError):
            body_length = -1
        if body_length < 0 or body_length > proxy.max_body_bytes:
            proxy._count("rejected")
            self._reject(413 if body_length > proxy.max_body_bytes else 400)
            return
        body = self.rfile.read(body_length)
        if len(body) != body_length:
            proxy._count("rejected")
            self._reject(400)
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().casefold() != "application/json":
            proxy._count("rejected")
            self._reject(415)
            return
        try:
            _parsed_body = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            proxy._count("rejected")
            self._reject(400)
            return
        if not isinstance(_parsed_body, dict):
            proxy._count("rejected")
            self._reject(400)
            return
        try:
            status, headers, response = proxy.forward(body)
        except DeepSeekProviderProxyError:
            proxy._count("upstream_errors")
            proxy._signal_failure("provider-proxy-upstream-failed")
            self._reject(502)
            return
        proxy._record_status(status)
        if status >= 400:
            proxy._signal_failure("provider-proxy-upstream-status")
        self.send_response(status)
        self.send_header("Content-Type", headers.get("content-type", "application/json"))
        if "content-length" in headers:
            self.send_header("Content-Length", headers["content-length"])
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            for chunk in response:
                if chunk:
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            # Client disconnects are a bounded transport counter, not an error
            # containing provider-controlled text.
            proxy._count("client_disconnects")
        finally:
            try:
                response.close()
            except Exception:
                pass
            proxy._count("requests")


class _ProxyHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address: tuple[str, int], proxy: "DeepSeekProviderProxy") -> None:
        self.proxy = proxy
        super().__init__(address, _ProxyHandler)


class DeepSeekProviderProxy:
    """One loopback proxy with a mutable, non-exported upstream key."""

    def __init__(
        self,
        credential: bytes | bytearray,
        *,
        upstream_url: str = DEEPSEEK_UPSTREAM_URL,
        host: str = "127.0.0.1",
        port: int = 0,
        max_body_bytes: int = DEEPSEEK_PROXY_MAX_BODY_BYTES,
        connect_timeout: float = 15.0,
        read_timeout: float = 330.0,
        on_failure: Callable[[str], None] | None = None,
    ) -> None:
        if not isinstance(credential, (bytes, bytearray)) or not credential:
            raise DeepSeekProviderProxyError("DeepSeek proxy credential is unavailable")
        parsed = urlsplit(upstream_url)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.path != "/responses":
            raise DeepSeekProviderProxyError("DeepSeek upstream URL is invalid")
        if parsed.scheme != "https" and upstream_url == DEEPSEEK_UPSTREAM_URL:
            raise DeepSeekProviderProxyError("DeepSeek upstream TLS is required")
        self._credential = bytearray(credential)
        self.upstream_url = upstream_url
        self.host = host
        self.port = port
        self.max_body_bytes = max(1, int(max_body_bytes))
        self.connect_timeout = max(0.1, float(connect_timeout))
        self.read_timeout = max(0.1, float(read_timeout))
        self.on_failure = on_failure
        self._server: _ProxyHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._counts: dict[str, int] = {
            "requests": 0,
            "rejected": 0,
            "upstream_errors": 0,
            "client_disconnects": 0,
        }
        self._last_stop_report: dict[str, bool | int] = {
            "shutdown_ok": True,
            "server_close_ok": True,
            "thread_joined": True,
            "thread_alive": False,
            "socket_open": False,
            "lifecycle_failure": False,
        }

    @property
    def base_url(self) -> str:
        server = self._server
        if server is None:
            raise DeepSeekProviderProxyError("DeepSeek proxy is not started")
        host, port = server.server_address
        return f"http://{host}:{port}"

    def _count(self, key: str) -> None:
        with self._lock:
            self._counts[key] = self._counts.get(key, 0) + 1

    def _signal_failure(self, reason_code: str) -> None:
        callback = self.on_failure
        if callable(callback):
            try:
                callback(reason_code)
            except Exception:
                pass

    def _record_status(self, status: int) -> None:
        category = "upstream_status_other"
        if 200 <= status < 300:
            category = "upstream_status_2xx"
        elif 400 <= status < 500:
            category = "upstream_status_4xx"
        elif status >= 500:
            category = "upstream_status_5xx"
        self._count(category)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {**self._counts, "listening": self._server is not None}

    def stop_snapshot(self) -> dict[str, bool | int]:
        """Return a safe immutable copy of the last shutdown outcome."""

        with self._lock:
            return dict(self._last_stop_report)

    def clear_secret(self) -> None:
        """Overwrite the mutable credential buffer, even after teardown errors."""

        with self._lock:
            for index in range(len(self._credential)):
                self._credential[index] = 0

    def secret_snapshot(self) -> bytes:
        with self._lock:
            value = bytes(self._credential)
            return b"" if not any(value) else value

    def start(self) -> str:
        with self._lock:
            if self._server is not None:
                return self.base_url
            try:
                server = _ProxyHTTPServer((self.host, self.port), self)
            except OSError as exc:
                raise DeepSeekProviderProxyError("DeepSeek proxy bind failed") from exc
            self._server = server
            thread = threading.Thread(
                target=server.serve_forever,
                name="formal-deepseek-provider-proxy",
                daemon=True,
            )
            self._thread = thread
            thread.start()
            return self.base_url

    def forward(self, body: bytes) -> tuple[int, dict[str, str], Any]:
        parsed = urlsplit(self.upstream_url)
        host = parsed.hostname
        if not host:
            raise DeepSeekProviderProxyError("DeepSeek upstream URL is invalid")
        with self._lock:
            key = bytes(self._credential)
        if not key:
            raise DeepSeekProviderProxyError("DeepSeek proxy credential is unavailable")
        connection: http.client.HTTPConnection | http.client.HTTPSConnection
        try:
            if parsed.scheme == "https":
                connection = http.client.HTTPSConnection(
                    host,
                    parsed.port or 443,
                    timeout=self.connect_timeout,
                    context=ssl.create_default_context(),
                )
            else:
                connection = http.client.HTTPConnection(
                    host,
                    parsed.port or 80,
                    timeout=self.connect_timeout,
                )
            connection.request(
                "POST",
                parsed.path or "/responses",
                body=body,
                headers={
                    "Authorization": "Bearer " + key.decode("utf-8", "strict"),
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "ontology-platform-modeling-team",
                    "Content-Length": str(len(body)),
                },
            )
            response = connection.getresponse()
            response_socket = getattr(connection, "sock", None)
            if response_socket is not None:
                response_socket.settimeout(self.read_timeout)
            safe_headers = {
                name.casefold(): value
                for name, value in response.getheaders()
                if name.casefold() in {"content-type", "content-length"}
            }
            return response.status, safe_headers, response
        except (OSError, UnicodeError, ValueError) as exc:
            try:
                connection.close()
            except Exception:
                pass
            raise DeepSeekProviderProxyError("DeepSeek upstream request failed") from exc

    def stop(self) -> bool:
        """Best-effort listener teardown with a safe lifecycle result.

        Every shutdown step is attempted independently.  A failed ``shutdown`` or
        join must not prevent ``server_close`` or credential wiping; the caller
        can use the returned boolean/``stop_snapshot`` to fail closed.
        """

        report: dict[str, bool | int] = {
            "shutdown_ok": True,
            "server_close_ok": True,
            "thread_joined": True,
            "thread_alive": False,
            "socket_open": False,
            "lifecycle_failure": False,
        }
        with self._lock:
            server = self._server
            thread = self._thread
        try:
            if server is not None:
                try:
                    server.shutdown()
                except Exception:
                    report["shutdown_ok"] = False
                try:
                    server.server_close()
                except Exception:
                    report["server_close_ok"] = False
                socket_obj = getattr(server, "socket", None)
                try:
                    report["socket_open"] = bool(
                        socket_obj is not None and socket_obj.fileno() >= 0
                    )
                except Exception:
                    report["socket_open"] = True
            if thread is not None and thread is not threading.current_thread():
                try:
                    thread.join(timeout=2.0)
                except Exception:
                    report["thread_joined"] = False
            try:
                report["thread_alive"] = bool(thread is not None and thread.is_alive())
            except Exception:
                report["thread_alive"] = True
        finally:
            with self._lock:
                self._server = None
                self._thread = None
                self.clear_secret()
                report["lifecycle_failure"] = not (
                    bool(report["shutdown_ok"])
                    and bool(report["server_close_ok"])
                    and bool(report["thread_joined"])
                    and not bool(report["thread_alive"])
                    and not bool(report["socket_open"])
                )
                self._last_stop_report = dict(report)
        return not bool(report["lifecycle_failure"])


__all__ = [
    "DEEPSEEK_API_KEY_ENV",
    "DEEPSEEK_CREDENTIAL_PATH",
    "DEEPSEEK_PROXY_MAX_BODY_BYTES",
    "DEEPSEEK_UPSTREAM_URL",
    "DeepSeekCredentialBinding",
    "DeepSeekCredentialError",
    "DeepSeekProviderProxy",
    "DeepSeekProviderProxyError",
    "preflight_deepseek_credential",
    "read_deepseek_credential",
]
