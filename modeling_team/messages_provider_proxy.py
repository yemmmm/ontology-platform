"""Narrow Host-held DeepSeek Messages transport; no protocol/model translation."""

from __future__ import annotations

import hmac
import http.client
import json
import secrets
import ssl
from http.server import BaseHTTPRequestHandler

from .deepseek_provider_proxy import ResponsesProviderSession


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
            json.loads(body)
        except (ValueError, UnicodeError):
            self.send_error(400)
            return
        headers = {
            key.lower(): value
            for key, value in self.headers.items()
            if key.lower() in {"anthropic-version", "anthropic-beta", "x-request-id"}
        }
        connection = http.client.HTTPSConnection(
            "api.deepseek.com",
            timeout=session.connect_timeout,
            context=ssl.create_default_context(),
        )
        response = None
        started = False
        status = None
        receipt = {
            "event": "attempt_start",
            "provider_id": session.provider_id,
            "usage_session_id": session._usage_session_id,
        }
        session.record_attempt(receipt)
        try:
            headers.update(
                {
                    "x-api-key": session.secret_snapshot().decode(),
                    "content-type": "application/json",
                    "accept": "text/event-stream",
                }
            )
            connection.request("POST", "/anthropic/v1/messages", body=body, headers=headers)
            if connection.sock is not None:
                connection.sock.settimeout(session.read_timeout)
            response = connection.getresponse()
            status = response.status
            self.send_response(status)
            for key, value in response.getheaders():
                if key.lower() in {"content-type", "retry-after", "request-id", "x-request-id"}:
                    self.send_header(key, value)
            self.send_header("Connection", "close")
            self.end_headers()
            started = True
            if status >= 400:
                # Keep the first HTTP cause, never echo provider bodies or credentials.
                self.wfile.write(
                    json.dumps(
                        {
                            "type": "error",
                            "error": {
                                "type": "provider_http_error",
                                "message": f"DeepSeek HTTP {status}",
                            },
                        }
                    ).encode()
                )
            else:
                while chunk := response.read1(65536):
                    self.wfile.write(chunk)
                    self.wfile.flush()
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
            session.record_attempt(
                {
                    **receipt,
                    "event": "attempt_end",
                    "http_status": status,
                    "stream_started": started,
                }
            )


class MessagesProviderSession(ResponsesProviderSession):
    handler_class = _MessagesHandler

    def __init__(self, credential, **kwargs):
        # Reuse listener lifecycle/secret wiping only. The handler fixes its TLS Messages upstream.
        super().__init__(
            credential, provider_id="deepseek-official", max_upstream_attempts=1, **kwargs
        )
        self.proxy_token = secrets.token_urlsafe(32)

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
