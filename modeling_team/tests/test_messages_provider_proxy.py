import http.client
import json
from unittest.mock import patch

import pytest

from modeling_team.messages_provider_proxy import MessagesProviderSession


class Response:
    def __init__(self, status=200, chunks=(b"data: first\n\n", b"data: last\n\n"), broken=False):
        self.status = status
        self.chunks = iter(chunks)
        self.broken = broken

    def getheaders(self):
        return [
            ("Content-Type", "text/event-stream"),
            ("x-request-id", "upstream-test"),
            ("Retry-After", "2"),
        ]

    def read1(self, size):
        value = next(self.chunks, b"")
        if not value and self.broken:
            raise OSError("stream failed")
        return value

    def close(self):
        pass


def request(session, body=b'{"model":"deepseek-flash","stream":true}', **headers):
    connection = http.client.HTTPConnection("127.0.0.1", session.bound_port, timeout=3)
    connection.request(
        "POST",
        "/v1/messages",
        body,
        headers={
            "x-api-key": session.proxy_token,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "tool-changes",
            **headers,
        },
    )
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    connection.close()
    return result


@pytest.mark.parametrize("status", [200, 401, 402, 429, 503])
def test_fixed_messages_tls_headers_exact_stream_and_original_status(status):
    calls = []

    class Connection:
        sock = None

        def __init__(self, host, **kwargs):
            assert host == "api.deepseek.com"
            assert "context" in kwargs

        def request(self, method, path, body, headers):
            calls.append((method, path, body, headers))

        def getresponse(self):
            return Response(status)

        def close(self):
            pass

    session = MessagesProviderSession(b"test-host-secret")
    session.start()
    try:
        with patch("modeling_team.messages_provider_proxy.http.client.HTTPSConnection", Connection):
            code, headers, body = request(session, Authorization="Bearer untrusted")
        assert code == status
        assert headers["x-request-id"] == "upstream-test"
        assert len(calls) == 1
        method, path, payload, sent = calls[0]
        assert path == "/anthropic/v1/messages"
        assert sent["x-api-key"] == "test-host-secret"
        assert "Authorization" not in sent
        assert sent["anthropic-version"] == "2023-06-01"
        assert sent["anthropic-beta"] == "tool-changes"
        assert json.loads(payload)["model"] == "deepseek-flash"
        assert b"test-host-secret" not in body
        if status == 200:
            assert body == b"data: first\n\ndata: last\n\n"
        else:
            assert f"HTTP {status}".encode() in body
    finally:
        assert session.stop()
    assert session.secret_snapshot() == b"" and session.proxy_token == ""


def test_interrupted_stream_is_closed_once_without_replay():
    calls = []

    class Connection:
        sock = None

        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            calls.append(1)

        def getresponse(self):
            return Response(chunks=(b"data: partial\n\n",), broken=True)

        def close(self):
            pass

    session = MessagesProviderSession(b"test-key")
    session.start()
    try:
        with patch("modeling_team.messages_provider_proxy.http.client.HTTPSConnection", Connection):
            code, _, body = request(session)
        assert code == 200 and body == b"data: partial\n\n"
        assert calls == [1]
        assert session.snapshot()["upstream_errors"] == 1
    finally:
        session.stop()


def test_proxy_credential_required_and_body_bounded():
    session = MessagesProviderSession(b"test-key", max_body_bytes=20)
    session.start()
    try:
        assert request(session, **{"x-api-key": "wrong"})[0] == 403
        assert request(session, body=b"x" * 21)[0] == 413
        assert request(session, body=b"invalid")[0] == 400
    finally:
        session.stop()


def test_host_key_repair_preserves_proxy_address_and_role_credential():
    session = MessagesProviderSession(b"old-test-key")
    session.start()
    try:
        address, token = session.base_url, session.proxy_token
        session.refresh_credential(b"repaired-test-key")
        assert session.base_url == address and session.proxy_token == token
        assert session.secret_snapshot() == b"repaired-test-key"
    finally:
        session.stop()
    assert session.secret_snapshot() == b""
