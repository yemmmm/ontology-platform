"""Narrow Host-held DeepSeek Messages transport; no protocol/model translation."""

from __future__ import annotations

import hmac
import http.client
import json
import logging
import queue
import re
import threading
import secrets
import ssl
import uuid
from http.server import BaseHTTPRequestHandler

from .deepseek_provider_proxy import ResponsesProviderSession
from .model_routing import PROVIDER_CATALOG
from .dsh_usage import MessagesUsageObserver, safe_id
from .usage_capture import identity, utc_now

LOG = logging.getLogger(__name__)


def _provider_error(response, status):
    """Inspect a bounded failure body, exporting only fixed categories, never its text."""
    raw = bytearray()
    try:
        while len(raw) <= 4096:
            chunk = response.read1(4097 - len(raw))
            if not chunk:
                break
            raw.extend(chunk[:4097 - len(raw)])
        value = json.loads(raw) if len(raw) <= 4096 else {}
        error = value.get("error", {}) if isinstance(value, dict) else {}
        if not isinstance(error, dict):
            error = {}
    except (ValueError, UnicodeError, OSError, http.client.HTTPException):
        error = {}
    provider_type = error.get("type")
    allowed_types = {"invalid_request_error", "authentication_error", "permission_error",
                     "rate_limit_error", "api_error", "overloaded_error", "billing_error"}
    if not isinstance(provider_type, str) or provider_type not in allowed_types:
        provider_type = None
    detail = " ".join(str(error.get(key, "")) for key in ("code", "message")).lower()
    if re.search(r"context[_ ](?:length|window).*(?:exceed|limit)|maximum context length|too many tokens", detail):
        reason = "context_window_exceeded"
    elif ("tool_result" in detail or "tool result" in detail) and (
        "tool_use" in detail or "tool call" in detail
    ):
        reason = "invalid_tool_history"
    elif status in {401, 403}:
        reason = "authentication"
    elif status == 402:
        reason = "quota"
    elif status == 429:
        reason = "rate_limit"
    elif status >= 500:
        reason = "server"
    else:
        reason = "invalid_request"
    return {"reason_code": reason, "provider_type": provider_type}


class _MessagesHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_POST(self):
        session = self.server.session
        if self.path != "/v1/messages" or not hmac.compare_digest(
            self.headers.get("x-api-key", ""), session.proxy_token
        ):
            self.send_error(403)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            size = 0
        if not 0 < size <= session.max_body_bytes:
            self.send_error(413)
            return
        body = self.rfile.read(size)
        try:
            request = json.loads(body)
            if not isinstance(request, dict):
                raise ValueError
        except (ValueError, UnicodeError):
            self.send_error(400)
            return
        headers = {
            key.lower(): value
            for key, value in self.headers.items()
            if key.lower() in {"anthropic-version", "anthropic-beta", "x-request-id"}
        }
        response = None
        started = False
        status = None
        observer = None if session.provider_id == "glm-messages" else MessagesUsageObserver()
        native_session = safe_id(self.headers.get("x-deepseek-harness-session-id"))
        with session._lock:
            binding = dict(session._usage_bindings.get(native_session, {}))
        receipt = {
            **binding,
            "runtime": "dsh",
            "runtime_session_id": native_session,
            "provider": session.provider_id,
            "request_id": uuid.uuid4().hex,
            "proxy_session_id": session._usage_session_id,
            "attempt_index": 1,
            "requested_model": safe_id(request.get("model")),
            "purpose": "compaction" if self.headers.get("x-deepseek-harness-compact") == "1"
                       else "assistant",
            "start": utc_now(),
            "status": "unfinished",
            "event": "attempt_start",
            "provider_id": session.provider_id,
            "usage_session_id": session._usage_session_id,
        }
        if not session.admit_attempt(receipt):
            self.send_response(402)
            self.send_header("Connection", "close")
            self.send_header("Content-Length", "0")
            self.end_headers()
            self.close_connection = True
            return
        connection = http.client.HTTPSConnection(
            session.upstream_host,
            timeout=session.connect_timeout,
            context=ssl.create_default_context(),
        )
        session.record_attempt(receipt)
        outcome = "transport_error"
        headers_at = provider_request_id = None
        client_write = False
        diagnostic = None
        request_shape = {
            "body_bytes": len(body),
            "message_count": len(request["messages"]) if isinstance(request.get("messages"), list) else None,
            "tool_count": len(request["tools"]) if isinstance(request.get("tools"), list) else None,
            "max_tokens": request.get("max_tokens") if type(request.get("max_tokens")) is int else None,
        }
        try:
            headers.update(
                {
                    "x-api-key": session.secret_snapshot().decode(),
                    "content-type": "application/json",
                    "accept": "text/event-stream",
                }
            )
            connection.request("POST", session.upstream_path, body=body, headers=headers)
            if connection.sock is not None:
                connection.sock.settimeout(session.read_timeout)
            response = connection.getresponse()
            status = response.status
            headers_at = utc_now()
            provider_request_id = next((safe_id(value) for key, value in response.getheaders()
                                        if key.lower() in {"request-id", "x-request-id"}), None)
            outcome = "http_error" if status >= 400 else "stream_error"
            if status >= 400:
                diagnostic = _provider_error(response, status)
            self.send_response(status)
            for key, value in response.getheaders():
                if key.lower() in {"content-type", "retry-after", "request-id", "x-request-id"}:
                    self.send_header(key, value)
            self.send_header("Connection", "close")
            self.end_headers()
            started = True
            if status >= 400:
                # The SDK can classify the real failure without receiving private error text.
                self.wfile.write(
                    json.dumps(
                        {
                            "type": "error",
                            "error": {
                                "type": diagnostic["provider_type"] or "provider_http_error",
                                "code": diagnostic["reason_code"],
                                "message": f"Provider HTTP {status}: "
                                           + diagnostic["reason_code"].replace("_", " "),
                            },
                            "request_shape": request_shape,
                        }
                    ).encode()
                )
            else:
                while chunk := response.read1(65536):
                    client_write = True
                    self.wfile.write(chunk)
                    self.wfile.flush()
                    client_write = False
                    if observer is not None:
                        # Observation never changes forwarded bytes or triggers another request.
                        try:
                            observer.feed(chunk)
                        except Exception:
                            observer.disabled = True
                            observer.issues.add("invalid_sse_event")
                outcome = "completed"
        except (BrokenPipeError, ConnectionResetError):
            outcome = "client_disconnected" if client_write else outcome
            session._count("upstream_errors")
        except (OSError, http.client.HTTPException):
            session._count("upstream_errors")
            if not started:
                self.send_error(502, "provider transport failed")
            # Once streaming begins, close. Never replay a possibly executed request.
        finally:
            self.close_connection = True
            if response is not None:
                response.close()
            connection.close()
            session._count("requests")
            end = utc_now()
            if observer is not None:
                session.record_attempt({
                    **receipt, **observer.finish(), "event": "response_usage",
                    "headers_at": headers_at, "provider_request_id": provider_request_id,
                    "end": end, "status": outcome, "http_status": status,
                    "time_basis": "usage_completion", "clock_ref": "host-utc",
                    **({"provider_error": diagnostic, "request_shape": request_shape}
                       if diagnostic is not None else {}),
                })
            session.record_attempt(
                {
                    **receipt,
                    "event": "attempt_end",
                    "http_status": status,
                    "stream_started": started,
                    "headers_at": headers_at, "end": end, "status": outcome,
                    **({"provider_error": diagnostic, "request_shape": request_shape}
                       if diagnostic is not None and observer is None else {}),
                }
            )


class MessagesProviderSession(ResponsesProviderSession):
    handler_class = _MessagesHandler

    def __init__(self, credential, *, provider_id="deepseek-official", **kwargs):
        from urllib.parse import urlsplit

        route = PROVIDER_CATALOG.get(provider_id)
        if route is None or route.wire_api != "messages":
            raise ValueError("unsupported-runtime-provider: expected a catalog Messages route")
        upstream = urlsplit(route.upstream_url)
        self.upstream_host, self.upstream_path = upstream.hostname, upstream.path
        # Reuse listener lifecycle/secret wiping only. The handler fixes its TLS Messages upstream.
        super().__init__(
            credential, provider_id=provider_id, max_upstream_attempts=1, **kwargs
        )
        self.upstream_url = route.upstream_url
        self.proxy_token = secrets.token_urlsafe(32)
        self._usage_bindings = {}
        self._capture_queue = queue.Queue(maxsize=1024)
        self._capture_stop = threading.Event()
        self._capture_thread = threading.Thread(target=self._write_usage, daemon=True,
                                                name="messages-numeric-receipts")
        self._capture_thread.start()

    def record_attempt(self, event):
        event = self.stamp_attempt(event)
        if self._capture_stop.is_set():
            self._count("usage_capture_dropped")
            LOG.warning("usage_capture_incomplete")
            return
        try:
            self._capture_queue.put_nowait((self.on_attempt, dict(event)))
        except queue.Full:
            self._count("usage_capture_dropped")
            LOG.warning("usage_capture_incomplete")

    def _write_usage(self):
        while not self._capture_stop.is_set() or not self._capture_queue.empty():
            try:
                callback, event = self._capture_queue.get(timeout=.1)
            except queue.Empty:
                continue
            if callback is not None:
                try:
                    callback(event)
                except Exception:
                    LOG.warning("usage_capture_incomplete")



    def register_usage_session(self, runtime_session_id, context, *, evidence_ref):
        """Host registers the actual session before admitting model input; never guesses."""
        if not safe_id(runtime_session_id) or not evidence_ref:
            LOG.warning("usage_capture_incomplete")
            return False
        with self._lock:
            self._usage_bindings[runtime_session_id] = {
                **identity(context), "binding_evidence_ref": evidence_ref,
                "runtime": "dsh", "runtime_session_id": runtime_session_id,
            }
        return True

    def refresh_credential(self, credential):
        """Host-only key repair; keep the listening URL and role proxy token stable."""
        if not isinstance(credential, (bytes, bytearray)) or not credential:
            raise ValueError("provider credential is unavailable")
        with self._lock:
            self.clear_secret()
            self._credential = bytearray(credential)

    def stop(self):
        try:
            return super().stop()
        finally:
            self.proxy_token = ""
            self._capture_stop.set()
            self._capture_thread.join(timeout=1)
            if self._capture_thread.is_alive():
                self._count("usage_capture_dropped")
                LOG.warning("usage_capture_incomplete")
