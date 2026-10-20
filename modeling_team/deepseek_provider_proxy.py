"""Runner-owned provider credential binding and loopback Responses sessions.

The formal Team never gives a provider credential to a Codex process.  This module
keeps the only copy in a mutable byte buffer owned by one short-lived loopback
Responses session, and validates the external file again immediately before
reading it.  The generic session is provider-neutral (R2.3-007); DeepSeek keeps a
thin compatibility wrapper plus its fixed credential contract.

The credential contract is provider-neutral too: a route supplies its own env var
name, default path, and label, while every route shares one set of file-identity
rules and one error type.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import select
import socket
import ssl
import stat
import threading
import time
import uuid

from dataclasses import dataclass
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.parse import urlsplit

from .usage_capture import LOG, utc_now


DEEPSEEK_API_KEY_ENV = "DEEPSEEK_API_KEY"
DEEPSEEK_CREDENTIAL_PATH = Path(
    "~/.config/ontology-platform/modeling-team-deepseek.env"
).expanduser()
DEEPSEEK_UPSTREAM_URL = "https://api.deepseek.com/responses"
GLM_API_KEY_ENV = "GLM_API_KEY"
GLM_CREDENTIAL_PATH = Path("~/.config/ontology-platform/modeling-team-glm.env").expanduser()
GLM_UPSTREAM_URL = "https://open.bigmodel.cn/api/v1/responses"
DEEPSEEK_PROXY_MAX_BODY_BYTES = 32 * 1024 * 1024
RESPONSES_SESSION_MAX_BODY_BYTES = DEEPSEEK_PROXY_MAX_BODY_BYTES
RESPONSES_UPSTREAM_FAILURE = "provider-upstream-failed"
RESPONSES_CLEANUP_FAILURE = "provider-session-cleanup-failed"
# 2026-09-17 abort-park fix: the upstream fuse is a bounded in-request retry, not
# a run kill.  Transient upstream rejections (429/5xx/transport drop) are retried
# inside the same client request with exponential backoff; only exhausting that
# budget advances the consecutive-failure counter by exactly one.
RESPONSES_UPSTREAM_MAX_ATTEMPTS = 3
RESPONSES_UPSTREAM_RETRY_BACKOFF_SECONDS = (2.0, 4.0, 8.0)
RESPONSES_UPSTREAM_RETRY_AFTER_CEILING_SECONDS = 60.0
_LOCAL_FAILURE_STATUS = 502
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_CREDENTIAL_MAX_BYTES = 4096
# Upstream response headers the session may read.  ``retry-after`` is a numeric
# delay, never provider free text, and is not forwarded to the local client.
_SAFE_UPSTREAM_HEADERS = frozenset({"content-type", "content-length", "retry-after"})


def _is_retryable_upstream_status(status: int) -> bool:
    """Whether one upstream HTTP status is a transient, backoff-retryable rejection.

    Only the fuse statuses (429 and the 5xx range) are retried; a 4xx other than
    a rate limit is a structural rejection the provider would repeat verbatim.
    """

    return status == 429 or 500 <= status <= 599


class ProviderCredentialError(RuntimeError):
    """Typed, provider-text-free credential validation failure."""


# Compatibility alias: every route shares one credential error type, so callers
# that catch the DeepSeek name keep catching provider-neutral failures.
DeepSeekCredentialError = ProviderCredentialError


class ProviderSessionError(RuntimeError):
    """Typed loopback Responses session startup/transport failure.

    ``transient`` marks a transport failure that is safe to retry inside the
    same client request; structural failures (credential unavailable, invalid
    upstream) are never retried.
    """

    def __init__(self, message: str, *, transient: bool = False) -> None:
        super().__init__(message)
        self.transient = transient


# Compatibility alias: the DeepSeek proxy error type is the session error type.
DeepSeekProviderProxyError = ProviderSessionError


@dataclass(frozen=True)
class ProviderCredentialContract:
    """Provider-neutral external credential file contract.

    The loopback session is provider-neutral (R2.3-007); each route brings its own
    env var name, default path, and label.  The validation rules themselves stay
    shared so adding a route cannot weaken them.
    """

    provider_id: str
    label: str
    env_var: str
    default_path: Path

    def error(self, detail: str) -> ProviderCredentialError:
        # Message shape is "<Label> credential <detail>"; callers and tests match
        # on the trailing detail, so keep those suffixes stable.
        return ProviderCredentialError(f"{self.label} credential {detail}")


DEEPSEEK_CREDENTIAL_CONTRACT = ProviderCredentialContract(
    provider_id="deepseek-direct",
    label="DeepSeek",
    env_var=DEEPSEEK_API_KEY_ENV,
    default_path=DEEPSEEK_CREDENTIAL_PATH,
)
GLM_CREDENTIAL_CONTRACT = ProviderCredentialContract(
    provider_id="glm-direct",
    label="GLM",
    env_var=GLM_API_KEY_ENV,
    default_path=GLM_CREDENTIAL_PATH,
)


@lru_cache(maxsize=None)
def _credential_assignment_re(env_var: str) -> re.Pattern[str]:
    # Assignment-only file: exactly `<ENV_VAR>=<value>` plus at most one trailing
    # newline.  Derived from the env var name so a route can never accept a
    # different provider's assignment.
    return re.compile(rf"{re.escape(env_var)}=([^\s\"'\r\n=]+)\n?\Z")


@dataclass(frozen=True)
class ProviderCredentialBinding:
    """Non-secret file identity frozen during Runner.prepare."""

    contract: ProviderCredentialContract
    path: Path
    st_dev: int
    st_ino: int
    st_size: int
    st_mtime_ns: int

    @property
    def canonical_path(self) -> str:
        return str(self.path)

    @property
    def key_ref(self) -> str:
        """Opaque reference to this verified file binding, without key bytes.

        This identifies the concrete Host credential binding, rather than a
        guessed provider account. Reopening that binding keeps the same
        reference; a changed file identity requires a new binding.
        """
        value = [self.contract.env_var, self.st_dev, self.st_ino, self.st_size, self.st_mtime_ns]
        digest = hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()
        return "credential-binding:" + digest

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


# Compatibility alias: the binding carries only non-secret file identity.
DeepSeekCredentialBinding = ProviderCredentialBinding


def _canonical_credential_path(
    contract: ProviderCredentialContract, path: Path | str | None
) -> Path:
    value = Path(path) if path is not None else contract.default_path
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
            raise contract.error("file is insecure")
        return expanded.resolve(strict=False)
    except ProviderCredentialError:
        raise
    except (OSError, RuntimeError) as exc:
        raise contract.error("path is invalid") from exc


def _validate_credential_bytes(contract: ProviderCredentialContract, payload: bytes) -> bytes:
    if not payload or len(payload) > _CREDENTIAL_MAX_BYTES:
        raise contract.error("file is malformed")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise contract.error("file is malformed") from exc
    match = _credential_assignment_re(contract.env_var).fullmatch(text)
    if match is None:
        raise contract.error("assignment is malformed")
    value = match.group(1)
    if not value or value.strip() != value:
        raise contract.error("assignment is malformed")
    return value.encode("utf-8")


def preflight_provider_credential(
    contract: ProviderCredentialContract, path: Path | str | None = None
) -> ProviderCredentialBinding:
    """Validate the contract's external file and return only non-secret metadata."""

    canonical = _canonical_credential_path(contract, path)
    try:
        metadata = os.lstat(canonical)
    except OSError as exc:
        raise contract.error("file is unavailable") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise contract.error("file is insecure")
    try:
        payload = canonical.read_bytes()
    except OSError as exc:
        raise contract.error("file is unreadable") from exc
    # Validate now but deliberately discard the value.  TeamRun/baseline/evidence
    # receives only this identity, never credential bytes or a digest.
    _validate_credential_bytes(contract, payload)
    return ProviderCredentialBinding(
        contract,
        canonical,
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
    )


def read_provider_credential(
    contract: ProviderCredentialContract, binding: ProviderCredentialBinding
) -> bytes:
    """Open with O_NOFOLLOW and revalidate the prepare-time identity."""

    if binding.contract.env_var != contract.env_var:
        # A binding made for one route must never be read under another's rules.
        raise contract.error("binding changed")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(binding.path, flags)
    except OSError as exc:
        raise contract.error("open failed") from exc
    try:
        metadata = os.fstat(descriptor)
        if not binding.metadata_matches(metadata):
            raise contract.error("binding changed")
        payload = os.read(descriptor, _CREDENTIAL_MAX_BYTES + 1)
        if len(payload) > _CREDENTIAL_MAX_BYTES:
            raise contract.error("file is malformed")
    except OSError as exc:
        raise contract.error("read failed") from exc
    finally:
        os.close(descriptor)
    return _validate_credential_bytes(contract, payload)


def preflight_deepseek_credential(
    path: Path | str | None = None,
) -> ProviderCredentialBinding:
    """DeepSeek compatibility wrapper over the provider-neutral contract."""

    return preflight_provider_credential(DEEPSEEK_CREDENTIAL_CONTRACT, path)


def read_deepseek_credential(binding: ProviderCredentialBinding) -> bytes:
    """DeepSeek compatibility wrapper over the provider-neutral contract."""

    return read_provider_credential(DEEPSEEK_CREDENTIAL_CONTRACT, binding)


def preflight_glm_credential(path: Path | str | None = None) -> ProviderCredentialBinding:
    """GLM compatibility wrapper over the provider-neutral contract."""

    return preflight_provider_credential(GLM_CREDENTIAL_CONTRACT, path)


def read_glm_credential(binding: ProviderCredentialBinding) -> bytes:
    """GLM compatibility wrapper over the provider-neutral contract."""

    return read_provider_credential(GLM_CREDENTIAL_CONTRACT, binding)


def _validate_upstream_url(upstream_url: str) -> None:
    parsed = urlsplit(upstream_url)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or not parsed.path
        or not parsed.path.endswith("/responses")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ProviderSessionError("provider upstream URL is invalid")
    if parsed.scheme != "https" and parsed.hostname not in _LOOPBACK_HOSTS:
        # Fixed TLS upstream: plain HTTP is accepted only for loopback test
        # upstreams, never for a real provider route.
        raise ProviderSessionError("provider upstream TLS is required")


class _SessionHandler(BaseHTTPRequestHandler):
    server_version = "ontology-platform-proxy"
    sys_version = ""

    def log_message(self, _format: str, *_args: object) -> None:
        # Never emit request paths, headers, provider errors, or body content.
        return

    @property
    def session(self) -> "ResponsesProviderSession":
        return self.server.session  # type: ignore[attr-defined,no-any-return]

    def _reject(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Connection", "close")
        self.send_header("Content-Length", "0")
        self.end_headers()
        self.close_connection = True

    def _discard_upstream_body(self, response: Any) -> None:
        # Consume and discard a non-2xx provider body: provider-controlled text
        # must never reach the local client, artifacts, or logs.
        try:
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
        except Exception:
            pass
        finally:
            try:
                response.close()
            except Exception:
                pass

    def _client_disconnected(self) -> bool:
        """Best-effort probe so a backoff retry never waits on a gone client.

        Only a confirmed close/reset suppresses the retry; every probe error
        keeps the retry (the bounded budget is the real backstop).
        """

        connection = getattr(self, "connection", None)
        if connection is None:
            return False
        try:
            readable, _, _ = select.select([connection], [], [], 0)
        except Exception:
            return False
        if not readable:
            return False
        try:
            return connection.recv(1, socket.MSG_PEEK) == b""
        except (BlockingIOError, InterruptedError):
            # Nothing buffered to read: the client is still waiting for us.
            return False
        except Exception:
            return True

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler hook
        session = self.session
        if self.path != "/responses":
            session._count("rejected")
            self._reject(404)
            return
        raw_length = self.headers.get("Content-Length")
        try:
            body_length = int(raw_length) if raw_length is not None else -1
        except (TypeError, ValueError):
            body_length = -1
        if body_length < 0 or body_length > session.max_body_bytes:
            session._count("rejected")
            self._reject(413 if body_length > session.max_body_bytes else 400)
            return
        body = self.rfile.read(body_length)
        if len(body) != body_length:
            session._count("rejected")
            self._reject(400)
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().casefold() != "application/json":
            session._count("rejected")
            self._reject(415)
            return
        try:
            _parsed_body = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            session._count("rejected")
            self._reject(400)
            return
        if not isinstance(_parsed_body, dict):
            session._count("rejected")
            self._reject(400)
            return
        request_id = uuid.uuid4().hex
        attempt = 1
        request_receipt = {"proxy_session_id": session._usage_session_id, "request_id": request_id,
                   "provider": session.provider_id,
                   "requested_model": _parsed_body.get("model")
                       if isinstance(_parsed_body.get("model"), str) else None,
                   "requested_effort": (_parsed_body.get("reasoning") or {}).get("effort")
                       if isinstance(_parsed_body.get("reasoning"), dict) else None}
        while True:
            receipt = {**request_receipt, "attempt_index": attempt, "start": utc_now()}
            if not session.admit_attempt(receipt, request=_parsed_body):
                self._reject(402)
                return
            session.record_attempt({**receipt, "event": "attempt_start", "status": "unfinished"})
            try:
                status, headers, response = session.forward(body)
            except ProviderSessionError as exc:
                session.record_attempt({**receipt, "event": "attempt_end", "end": utc_now(),
                                        "status": "transport_error"})
                if self._retry_transport_failure(session, attempt, exc):
                    attempt += 1
                    continue
                session._count("upstream_errors")
                session.note_upstream_failure()
                self._reject(_LOCAL_FAILURE_STATUS)
                return
            receipt.update(http_status=status, headers_at=utc_now())
            session._record_status(status)
            if 200 <= status < 300:
                break
            retry_after = headers.get("retry-after") if isinstance(headers, dict) else None
            self._discard_upstream_body(response)
            session.record_attempt({**receipt, "event": "attempt_end", "end": utc_now(),
                                    "status": "http_error"})
            if (
                _is_retryable_upstream_status(status)
                and attempt < session.max_upstream_attempts
                and not self._client_disconnected()
            ):
                # One client request stays one consecutive-failure decision:
                # the bounded backoff absorbs the transient rejection here.
                session._count("upstream_retries")
                time.sleep(session.upstream_retry_delay(attempt, retry_after))
                attempt += 1
                continue
            session._count("upstream_errors")
            session.note_upstream_failure()
            # Preserve only the upstream status after the bounded retry budget
            # is exhausted (or for an immediate structural 4xx).  The body,
            # headers, and reason phrase remain local and provider-text-free.
            self._reject(status)
            return
        session.note_upstream_success()
        stream_status = "completed"
        self.send_response(status)
        self.send_header("Content-Type", headers.get("content-type", "application/json"))
        if "content-length" in headers:
            self.send_header("Content-Length", headers["content-length"])
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            upstream = iter(response)
            while True:
                try:
                    chunk = next(upstream)
                except StopIteration:
                    break
                except (OSError, http.client.HTTPException):
                    # A 2xx stream broke before a successful terminal state.
                    # Already-transmitted model output stays transparent, so
                    # this failure is never retried; it is counted and only
                    # signals at the consecutive-failure threshold, never the
                    # exception string.
                    stream_status = "stream_error"
                    session._count("upstream_errors")
                    session.note_upstream_failure()
                    break
                if not chunk:
                    continue
                try:
                    self.wfile.write(chunk)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    # Client disconnects are a bounded transport counter, not an
                    # error containing provider-controlled text.
                    stream_status = "client_disconnected"
                    session._count("client_disconnects")
                    break
        finally:
            try:
                response.close()
            except Exception:
                pass
            session._count("requests")
            session.record_attempt({**receipt, "event": "attempt_end", "end": utc_now(),
                                    "status": stream_status})

    def _retry_transport_failure(
        self, session: "ResponsesProviderSession", attempt: int, exc: ProviderSessionError
    ) -> bool:
        """Retry one transient upstream transport failure inside this request."""

        if not getattr(exc, "transient", False):
            return False
        if attempt >= session.max_upstream_attempts or self._client_disconnected():
            return False
        session._count("upstream_retries")
        time.sleep(session.upstream_retry_delay(attempt, None))
        return True


class _SessionHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address: tuple[str, int], session: "ResponsesProviderSession") -> None:
        self.session = session
        super().__init__(address, getattr(session, "handler_class", _SessionHandler))


class ResponsesProviderSession:
    """One loopback Responses session with a mutable, non-exported upstream key.

    Only ``127.0.0.1:0`` listening, only bounded JSON ``POST /responses``,
    inbound Authorization replaced by the Host-owned key, fixed TLS upstream,
    safe response headers only, provider bodies never logged, and the key buffer
    overwritten on teardown.
    """

    def __init__(
        self,
        credential: bytes | bytearray,
        *,
        provider_id: str = "deepseek-direct",
        upstream_url: str = DEEPSEEK_UPSTREAM_URL,
        host: str = "127.0.0.1",
        port: int = 0,
        max_body_bytes: int = RESPONSES_SESSION_MAX_BODY_BYTES,
        connect_timeout: float = 15.0,
        # Per-read upstream socket timeout.  1250.0 is calibrated above the codex
        # adapter's 1200s LLM inactivity watchdog: glm-5.3-flash at max reasoning
        # effort can stay silent between streamed reasoning blocks for minutes
        # while the upstream is alive (observed 2026-09-11: three real starts hit
        # >300s silent blocks), and 330.0 killed the whole run with
        # provider-upstream-failed.  A genuinely dead connection still times out.
        read_timeout: float = 1250.0,
        # Consecutive upstream failures without a 2xx response before the
        # session signals provider-upstream-failed.  One transient upstream
        # error must not kill a whole real modeling run: the codex App Server
        # retries rejected/broken requests itself, and a later success resets
        # the counter.  Threshold 1 restores the historical fail-fast behavior
        # for focused tests.
        upstream_failure_threshold: int = 3,
        max_upstream_attempts: int = RESPONSES_UPSTREAM_MAX_ATTEMPTS,
        retry_backoff_seconds: Sequence[float] = RESPONSES_UPSTREAM_RETRY_BACKOFF_SECONDS,
        retry_after_ceiling_seconds: float = RESPONSES_UPSTREAM_RETRY_AFTER_CEILING_SECONDS,
        on_failure: Callable[[str], None] | None = None,
        on_attempt: Callable[[dict], None] | None = None,
        before_request: Callable[[dict], None] | None = None,
    ) -> None:
        if not isinstance(credential, (bytes, bytearray)) or not credential:
            raise ProviderSessionError("provider session credential is unavailable")
        if not provider_id or not isinstance(provider_id, str):
            raise ProviderSessionError("provider session identity is invalid")
        _validate_upstream_url(upstream_url)
        self.provider_id = provider_id
        self._credential = bytearray(credential)
        self.upstream_url = upstream_url
        self.host = host
        self.port = port
        self.max_body_bytes = max(1, int(max_body_bytes))
        self.connect_timeout = max(0.1, float(connect_timeout))
        self.read_timeout = max(0.1, float(read_timeout))
        self.upstream_failure_threshold = max(1, int(upstream_failure_threshold))
        self.max_upstream_attempts = max(1, int(max_upstream_attempts))
        self.retry_backoff_seconds = tuple(
            max(0.0, float(delay)) for delay in retry_backoff_seconds
        ) or (0.0,)
        self.retry_after_ceiling_seconds = max(0.0, float(retry_after_ceiling_seconds))
        self.bound_port: int | None = None
        self._consecutive_upstream_failures = 0
        self.on_failure = on_failure
        self.on_attempt = on_attempt
        self.before_request = before_request
        self._usage_session_id = uuid.uuid4().hex
        self._server: _SessionHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._attempt_clocks: dict[tuple, dict] = {}
        self._control_inputs: dict[str, str] = {}
        self._counts: dict[str, int] = {
            "requests": 0,
            "rejected": 0,
            "upstream_errors": 0,
            "upstream_retries": 0,
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
            raise ProviderSessionError("provider session is not started")
        host, port = server.server_address
        return f"http://{host}:{port}"

    def record_attempt(self, event: dict) -> None:
        event = self.stamp_attempt(event)
        if self.on_attempt is not None:
            try:
                self.on_attempt(event)
            except Exception:
                LOG.warning("usage_capture_incomplete")

    def authorize_control(self, text: str, control_id: str) -> None:
        """Allow one exact Host control input after durable native admission."""
        if not text or not control_id:
            raise ProviderSessionError("provider control binding is invalid")
        with self._lock:
            self._control_inputs[text] = control_id

    def admit_attempt(self, receipt: dict, *, request: dict | None = None) -> bool:
        """Check each real upstream attempt, including automatic retries.

        This is an admission boundary, separate from the advisory numeric
        observer. A local refusal is retained without inventing token usage or
        counting it as a provider failure.
        """
        if self.before_request is None:
            return True
        from .task_budget import BudgetError

        # The shared provider cannot identify a member from model alone.
        # Match only the exact new Host control input, once, rather than lend
        # a provider-wide exception to another member or an automatic retry.
        inputs = (request or {}).get("input")
        text = inputs if isinstance(inputs, str) else None
        if isinstance(inputs, list) and inputs and isinstance(inputs[-1], dict):
            last = inputs[-1]
            content = last.get("content") if last.get("role") == "user" else None
            if isinstance(content, str):
                text = content
            elif isinstance(content, list) and len(content) == 1 and isinstance(content[0], dict):
                if content[0].get("type") in {"input_text", "text"}:
                    text = content[0].get("text")
        with self._lock:
            control_id = self._control_inputs.pop(text, None) if isinstance(text, str) else None
        checked = dict(receipt)
        if control_id is not None:
            checked["_budget_control_admitted"] = True
            checked["_budget_control_id"] = control_id
        try:
            self.before_request(checked)
        except BudgetError:
            self._count("budget_rejected")
            self.record_attempt({
                **receipt, "event": "attempt_end", "end": utc_now(),
                "status": "not_admitted",
            })
            return False
        return True

    def stamp_attempt(self, event: dict) -> dict:
        from .close_statistics import clock_stamp
        key = (event.get("request_id"), event.get("attempt_index"))
        with self._lock:
            if event.get("event") == "attempt_start":
                stamp = clock_stamp()
                self._attempt_clocks[key] = {"clock_ref": stamp["clock_ref"],
                    "monotonic_start_ns": stamp["monotonic_ns"]}
            result = {**event, **self._attempt_clocks.get(key, {})}
            if event.get("event") == "attempt_end":
                result["monotonic_end_ns"] = clock_stamp()["monotonic_ns"]
                self._attempt_clocks.pop(key, None)
            return result

    def _count(self, key: str) -> None:
        with self._lock:
            self._counts[key] = self._counts.get(key, 0) + 1

    def _signal_failure(self, reason_code: str) -> None:
        # Only stable reason codes may leave the session; provider free text is
        # never forwarded to callbacks, clients, artifacts, or logs.
        if reason_code not in {RESPONSES_UPSTREAM_FAILURE, RESPONSES_CLEANUP_FAILURE}:
            return
        callback = self.on_failure
        if callable(callback):
            try:
                callback(reason_code)
            except Exception:
                pass

    def note_upstream_failure(self) -> None:
        """Count one consecutive upstream failure and signal at the threshold.

        The consecutive counter only advances on failures; every successful 2xx
        response (``note_upstream_success``) resets it.  The threshold keeps a
        single transient upstream error recoverable while a persistently dead
        upstream still fails the run with the stable reason code.
        """

        with self._lock:
            self._consecutive_upstream_failures += 1
            if self._consecutive_upstream_failures < self.upstream_failure_threshold:
                return
            self._consecutive_upstream_failures = 0
        self._signal_failure(RESPONSES_UPSTREAM_FAILURE)

    def note_upstream_success(self) -> None:
        with self._lock:
            self._consecutive_upstream_failures = 0

    def upstream_retry_delay(self, attempt: int, retry_after: str | None) -> float:
        """One bounded backoff delay, in seconds, for the next in-request attempt.

        A numeric ``Retry-After`` from the upstream wins but is clamped to the
        session ceiling (and never negative); without one, the exponential
        backoff ladder applies.  The ladder value is out-of-range safe so a
        misconfigured attempt index can never raise inside a request thread.
        """

        if retry_after is not None:
            try:
                return min(
                    self.retry_after_ceiling_seconds,
                    max(0.0, float(retry_after.strip())),
                )
            except ValueError:
                pass
        ladder = self.retry_backoff_seconds
        index = max(0, int(attempt) - 1)
        if not ladder:
            return 0.0
        return ladder[index] if index < len(ladder) else ladder[-1]

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
                server = _SessionHTTPServer((self.host, self.port), self)
            except OSError as exc:
                raise ProviderSessionError("provider session bind failed") from exc
            # Remember the last bound port so a dead session can be rebuilt on
            # the same loopback address the running app-servers already point
            # at, before falling back to an ephemeral port.
            self.bound_port = int(server.server_address[1])
            self._server = server
            thread = threading.Thread(
                target=server.serve_forever,
                name=f"formal-provider-session-{self.provider_id}",
                daemon=True,
            )
            self._thread = thread
            thread.start()
            return self.base_url

    def forward(self, body: bytes) -> tuple[int, dict[str, str], Any]:
        parsed = urlsplit(self.upstream_url)
        host = parsed.hostname
        if not host:
            raise ProviderSessionError("provider upstream URL is invalid")
        with self._lock:
            key = bytes(self._credential)
        if not key:
            raise ProviderSessionError("provider session credential is unavailable")
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
            # request() establishes TCP/TLS with connect_timeout.  Apply the
            # read timeout before waiting for headers, which can be delayed by
            # reasoning.  getresponse() also detaches Connection: close sockets,
            # so setting the timeout afterwards can miss the body socket too.
            response_socket = getattr(connection, "sock", None)
            if response_socket is not None:
                response_socket.settimeout(self.read_timeout)
            response = connection.getresponse()
            safe_headers = {
                name.casefold(): value
                for name, value in response.getheaders()
                if name.casefold() in _SAFE_UPSTREAM_HEADERS
            }
            return response.status, safe_headers, response
        except (OSError, http.client.HTTPException) as exc:
            # Transport-level failures (connect/reset/timeout/protocol) are the
            # transient class the in-request backoff may retry; a malformed key
            # (UnicodeError) or URL (ValueError) is structural and is not.
            try:
                connection.close()
            except Exception:
                pass
            raise ProviderSessionError(
                "provider upstream request failed", transient=True
            ) from exc
        except (UnicodeError, ValueError) as exc:
            try:
                connection.close()
            except Exception:
                pass
            raise ProviderSessionError("provider upstream request failed") from exc

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


class DeepSeekProviderProxy(ResponsesProviderSession):
    """Thin DeepSeek compatibility wrapper over the provider-neutral session."""

    def __init__(
        self,
        credential: bytes | bytearray,
        *,
        upstream_url: str = DEEPSEEK_UPSTREAM_URL,
        host: str = "127.0.0.1",
        port: int = 0,
        max_body_bytes: int = DEEPSEEK_PROXY_MAX_BODY_BYTES,
        connect_timeout: float = 15.0,
        # Same calibration as ResponsesProviderSession (see its read_timeout).
        read_timeout: float = 1250.0,
        upstream_failure_threshold: int = 3,
        max_upstream_attempts: int = RESPONSES_UPSTREAM_MAX_ATTEMPTS,
        retry_backoff_seconds: Sequence[float] = RESPONSES_UPSTREAM_RETRY_BACKOFF_SECONDS,
        retry_after_ceiling_seconds: float = RESPONSES_UPSTREAM_RETRY_AFTER_CEILING_SECONDS,
        on_failure: Callable[[str], None] | None = None,
        on_attempt: Callable[[dict], None] | None = None,
        before_request: Callable[[dict], None] | None = None,
    ) -> None:
        super().__init__(
            credential,
            provider_id="deepseek-direct",
            upstream_url=upstream_url,
            host=host,
            port=port,
            max_body_bytes=max_body_bytes,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
            upstream_failure_threshold=upstream_failure_threshold,
            max_upstream_attempts=max_upstream_attempts,
            retry_backoff_seconds=retry_backoff_seconds,
            retry_after_ceiling_seconds=retry_after_ceiling_seconds,
            on_failure=on_failure,
            on_attempt=on_attempt,
            before_request=before_request,
        )


__all__ = [
    "DEEPSEEK_API_KEY_ENV",
    "DEEPSEEK_CREDENTIAL_CONTRACT",
    "DEEPSEEK_CREDENTIAL_PATH",
    "DEEPSEEK_PROXY_MAX_BODY_BYTES",
    "DEEPSEEK_UPSTREAM_URL",
    "GLM_API_KEY_ENV",
    "GLM_CREDENTIAL_CONTRACT",
    "GLM_CREDENTIAL_PATH",
    "GLM_UPSTREAM_URL",
    "RESPONSES_SESSION_MAX_BODY_BYTES",
    "DeepSeekCredentialBinding",
    "DeepSeekCredentialError",
    "DeepSeekProviderProxy",
    "DeepSeekProviderProxyError",
    "ProviderCredentialBinding",
    "ProviderCredentialContract",
    "ProviderCredentialError",
    "ProviderSessionError",
    "RESPONSES_UPSTREAM_FAILURE",
    "RESPONSES_UPSTREAM_MAX_ATTEMPTS",
    "RESPONSES_UPSTREAM_RETRY_AFTER_CEILING_SECONDS",
    "RESPONSES_UPSTREAM_RETRY_BACKOFF_SECONDS",
    "RESPONSES_CLEANUP_FAILURE",
    "ResponsesProviderSession",
    "preflight_deepseek_credential",
    "preflight_glm_credential",
    "preflight_provider_credential",
    "read_deepseek_credential",
    "read_glm_credential",
    "read_provider_credential",
]
