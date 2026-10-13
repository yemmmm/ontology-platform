from __future__ import annotations

import http.client
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from modeling_team.deepseek_provider_proxy import (
    GLM_CREDENTIAL_CONTRACT,
    DeepSeekCredentialError,
    DeepSeekProviderProxy,
    ProviderCredentialError,
    ResponsesProviderSession,
    preflight_deepseek_credential,
    preflight_glm_credential,
    preflight_provider_credential,
    read_deepseek_credential,
    read_glm_credential,
)


class _UpstreamHandler(BaseHTTPRequestHandler):
    seen: list[tuple[str | None, str | None, bytes]] = []

    def do_POST(self) -> None:  # noqa: N802 - stdlib hook
        length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(length)
        self.seen.append(
            (self.headers.get("Authorization"), self.headers.get("X-Leak"), payload)
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *_args: object) -> None:
        return


@pytest.fixture()
def upstream():
    _UpstreamHandler.seen.clear()
    server = HTTPServer(("127.0.0.1", 0), _UpstreamHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def test_credential_preflight_and_runtime_revalidation_are_secret_free(tmp_path: Path) -> None:
    path = tmp_path / "deepseek.env"
    path.write_text("DEEPSEEK_API_KEY=credential-sentinel\n", encoding="utf-8")
    path.chmod(0o600)
    binding = preflight_deepseek_credential(path)
    assert "credential-sentinel" not in repr(binding)
    assert read_deepseek_credential(binding) == b"credential-sentinel"
    path.write_text("DEEPSEEK_API_KEY=changed\n", encoding="utf-8")
    path.chmod(0o600)
    with pytest.raises(DeepSeekCredentialError, match="binding changed"):
        read_deepseek_credential(binding)


def test_credential_preflight_rejects_final_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_text("DEEPSEEK_API_KEY=sentinel\n", encoding="utf-8")
    target.chmod(0o600)
    link = tmp_path / "deepseek.env"
    link.symlink_to(target)
    with pytest.raises(DeepSeekCredentialError, match="insecure"):
        preflight_deepseek_credential(link)


@pytest.mark.parametrize(
    "payload",
    [
        b"DEEPSEEK_API_KEY=\n",
        b"DEEPSEEK_API_KEY='quoted'\n",
        b"DEEPSEEK_API_KEY=one\nDEEPSEEK_API_KEY=two\n",
        b"LLM_API_KEY=legacy\n",
    ],
)
def test_credential_preflight_rejects_non_exact_assignments(tmp_path: Path, payload: bytes) -> None:
    path = tmp_path / "deepseek.env"
    path.write_bytes(payload)
    path.chmod(0o600)
    with pytest.raises(DeepSeekCredentialError):
        preflight_deepseek_credential(path)


def test_glm_credential_contract_accepts_only_its_own_assignment(tmp_path: Path) -> None:
    path = tmp_path / "glm.env"
    path.write_text("GLM_API_KEY=glm-credential-sentinel\n", encoding="utf-8")
    path.chmod(0o600)
    binding = preflight_glm_credential(path)
    assert "glm-credential-sentinel" not in repr(binding)
    assert read_glm_credential(binding) == b"glm-credential-sentinel"
    # Runtime revalidation still binds the frozen file identity.
    path.write_text("GLM_API_KEY=changed\n", encoding="utf-8")
    path.chmod(0o600)
    with pytest.raises(ProviderCredentialError, match="binding changed"):
        read_glm_credential(binding)


@pytest.mark.parametrize(
    "payload",
    [
        # Another provider's assignment, including the DeepSeek one the generic
        # validator used to hardcode.
        b"DEEPSEEK_API_KEY=deepseek-sentinel\n",
        b"LLM_API_KEY=legacy\n",
        b"GLM_API_KEY=\n",
        b"GLM_API_KEY='quoted'\n",
        b"GLM_API_KEY=one\nGLM_API_KEY=two\n",
        b"glm_api_key=lowercase\n",
    ],
)
def test_glm_credential_contract_rejects_foreign_or_malformed_assignments(
    tmp_path: Path, payload: bytes
) -> None:
    path = tmp_path / "glm.env"
    path.write_bytes(payload)
    path.chmod(0o600)
    with pytest.raises(ProviderCredentialError):
        preflight_glm_credential(path)


def test_glm_credential_contract_enforces_the_same_file_identity(tmp_path: Path) -> None:
    path = tmp_path / "glm.env"
    path.write_text("GLM_API_KEY=sentinel\n", encoding="utf-8")
    # Insecure mode: the generic rules are shared, not re-implemented per route.
    path.chmod(0o644)
    with pytest.raises(ProviderCredentialError, match="insecure"):
        preflight_glm_credential(path)

    # Final symlink is rejected before resolution.
    target = tmp_path / "target"
    target.write_text("GLM_API_KEY=sentinel\n", encoding="utf-8")
    target.chmod(0o600)
    link = tmp_path / "glm-link.env"
    link.symlink_to(target)
    with pytest.raises(ProviderCredentialError, match="insecure"):
        preflight_glm_credential(link)


def test_a_binding_never_crosses_between_credential_contracts(tmp_path: Path) -> None:
    # A GLM binding must not be readable under the DeepSeek contract, or vice
    # versa; the binding carries the contract it was made for.
    path = tmp_path / "glm.env"
    path.write_text("GLM_API_KEY=sentinel\n", encoding="utf-8")
    path.chmod(0o600)
    glm_binding = preflight_glm_credential(path)
    assert glm_binding.contract is GLM_CREDENTIAL_CONTRACT
    with pytest.raises(ProviderCredentialError, match="binding changed"):
        read_deepseek_credential(glm_binding)

    assert ProviderCredentialError is DeepSeekCredentialError
    with pytest.raises(ProviderCredentialError):
        preflight_provider_credential(
            type(GLM_CREDENTIAL_CONTRACT)(
                provider_id="glm-direct",
                label="GLM",
                env_var="GLM_API_KEY",
                default_path=tmp_path / "missing.env",
            )
        )


def test_provider_proxy_replaces_inbound_auth_and_streams_upstream(upstream) -> None:
    proxy = DeepSeekProviderProxy(
        b"file-only-sentinel",
        upstream_url=f"http://127.0.0.1:{upstream.server_port}/responses",
    )
    proxy.start()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", int(proxy.base_url.rsplit(":", 1)[1]))
        connection.request(
            "POST",
            "/responses",
            body=b"{}",
            headers={
                "Authorization": "Bearer inbound-sentinel",
                "X-Leak": "should-not-forward",
                "Content-Type": "application/json",
            },
        )
        response = connection.getresponse()
        assert response.status == 200
        assert response.read() == b"{}"
        connection.close()
    finally:
        proxy.stop()
    assert _UpstreamHandler.seen == [
        ("Bearer file-only-sentinel", None, b"{}")
    ]
    assert proxy.secret_snapshot() == b""


def test_provider_proxy_body_cap_fails_closed(upstream) -> None:
    proxy = DeepSeekProviderProxy(
        b"sentinel",
        upstream_url=f"http://127.0.0.1:{upstream.server_port}/responses",
        max_body_bytes=4,
    )
    proxy.start()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", int(proxy.base_url.rsplit(":", 1)[1]))
        connection.request("POST", "/responses", body=b"12345")
        response = connection.getresponse()
        assert response.status == 413
        response.read()
        connection.close()
    finally:
        proxy.stop()
    assert _UpstreamHandler.seen == []


def test_provider_proxy_rejects_malformed_body(upstream) -> None:
    proxy = DeepSeekProviderProxy(
        b"sentinel",
        upstream_url=f"http://127.0.0.1:{upstream.server_port}/responses",
    )
    proxy.start()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", int(proxy.base_url.rsplit(":", 1)[1]))
        connection.request(
            "POST",
            "/responses",
            body=b"not-json",
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        assert response.status == 400
        response.read()
        connection.close()
    finally:
        proxy.stop()
    assert _UpstreamHandler.seen == []


def test_provider_session_read_timeout_default_is_calibrated_above_watchdog() -> None:
    """The upstream read timeout must tolerate long max-effort silent blocks.

    2026-09-11 calibration: glm-5.3-flash at max reasoning effort stayed silent
    between streamed reasoning blocks for more than the previous 330.0s default,
    and three real starts died with provider-upstream-failed while the upstream
    was alive.  The default must sit above the codex adapter's 1200s LLM
    inactivity watchdog so the watchdog stays the authoritative hang guard.
    """

    session = ResponsesProviderSession(b"file-only-sentinel")
    try:
        assert session.read_timeout == 1250.0
    finally:
        session.stop()
    proxy = DeepSeekProviderProxy(b"file-only-sentinel")
    try:
        assert proxy.read_timeout == 1250.0
    finally:
        proxy.stop()


def _provider_timeout_probe(
    *, scheme: str = "https", header_delay: float = 30.0,
    body_delay: float = 45.0, read_timeout: float = 1250.0,
    connect_fails: bool = False,
) -> tuple[int, bytes, dict]:
    """Exercise the real POST handler with a deterministic, socket-free upstream.

    The real http.client connection/response enforce configured timeouts through
    an in-memory socket, including Connection: close socket detachment.
    No provider, business data, or credential file is accessed.
    """
    import io
    from types import SimpleNamespace
    from unittest.mock import patch

    from modeling_team.deepseek_provider_proxy import _SessionHandler

    observed = {}

    class TimeoutFile(io.BytesIO):
        def __init__(self, sock):
            super().__init__(
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                b"Content-Length: 2\r\nConnection: close\r\n\r\n{}"
            )
            self.sock = sock
            self.headers_complete = False

        def readline(self, size=-1):
            if self.tell() == 0:
                observed["header_timeout"] = self.sock.timeout
                if header_delay > self.sock.timeout:
                    raise TimeoutError("synthetic header timeout")
            if self.headers_complete:
                observed["body_timeout"] = self.sock.timeout
                if body_delay > self.sock.timeout:
                    raise TimeoutError("synthetic body timeout")
            line = super().readline(size)
            if line == b"\r\n":
                self.headers_complete = True
            return line

        def close(self):
            observed["response_closed"] = True
            super().close()

    class TimeoutSocket:
        def __init__(self, timeout):
            self.timeout = timeout

        def settimeout(self, timeout):
            self.timeout = timeout

        def sendall(self, payload):
            if payload.startswith(b"POST "):
                request_line = payload.split(b"\r\n", 1)[0].decode().split()
                observed["request_line"] = tuple(request_line[:2])
                assert b"Content-Length: " + str(len(body)).encode() in payload
            else:
                observed["request"] = (*observed["request_line"], payload)

        def makefile(self, mode):
            assert mode == "rb"
            return TimeoutFile(self)

        def close(self):
            observed["connection_closed"] = True

    def connect(connection):
        observed["connects"] = observed.get("connects", 0) + 1
        observed["connect_timeout"] = connection.timeout
        if connect_fails:
            raise TimeoutError("synthetic connect timeout")
        connection.sock = TimeoutSocket(connection.timeout)

    session = ResponsesProviderSession(
        b"synthetic-only", upstream_url=(
            "https://api.deepseek.com/responses" if scheme == "https"
            else "http://127.0.0.1:1/responses"
        ), connect_timeout=15.0, read_timeout=read_timeout, max_upstream_attempts=1,
    )
    body = b'{"model":"deepseek-v4-flash","reasoning":{"effort":"high"}}'
    handler = object.__new__(_SessionHandler)
    handler.server = SimpleNamespace(session=session)
    handler.path = "/responses"
    handler.headers = {"Content-Type": "application/json", "Content-Length": str(len(body))}
    handler.rfile = io.BytesIO(body)
    handler.wfile = io.BytesIO()
    handler.send_response = lambda status: observed.update(local_status=status)
    handler.send_header = lambda *_args: None
    handler.end_headers = lambda: None
    connection_type = http.client.HTTPSConnection if scheme == "https" else http.client.HTTPConnection
    try:
        with patch.object(connection_type, "connect", connect):
            handler.do_POST()
        observed["counts"] = session.snapshot()
        return observed["local_status"], handler.wfile.getvalue(), observed
    finally:
        session.stop()


def test_provider_timeout_covers_response_headers_without_changing_request() -> None:
    for scheme in ("https", "http"):
        status, body, observed = _provider_timeout_probe(scheme=scheme)
        assert status == 200
        assert body == b"{}"
        assert observed["connect_timeout"] == 15.0
        assert observed["header_timeout"] == 1250.0
        assert observed["connects"] == 1
        assert observed["request"] == (
            "POST", "/responses",
            b'{"model":"deepseek-v4-flash","reasoning":{"effort":"high"}}',
        )
        assert observed["counts"]["upstream_errors"] == 0
        assert observed["counts"]["upstream_retries"] == 0


def test_provider_timeout_survives_connection_close_socket_detachment() -> None:
    status, body, observed = _provider_timeout_probe(header_delay=0.0)
    assert status == 200
    assert body == b"{}"
    assert observed["body_timeout"] == 1250.0
    assert observed["response_closed"] is True
    assert observed["counts"]["upstream_errors"] == 0


def test_provider_timeout_keeps_connection_setup_bounded() -> None:
    status, body, observed = _provider_timeout_probe(connect_fails=True)
    assert status == 502
    assert body == b""
    assert observed["connect_timeout"] == 15.0
    assert "header_timeout" not in observed
    assert "request" not in observed
    assert observed["counts"]["upstream_errors"] == 1


def test_provider_timeout_still_rejects_headers_beyond_read_deadline() -> None:
    status, body, observed = _provider_timeout_probe(read_timeout=20.0)
    assert status == 502
    assert body == b""
    assert observed["header_timeout"] == 20.0
    assert observed["connection_closed"] is True
    assert observed["counts"]["upstream_errors"] == 1


def test_provider_timeout_still_counts_broken_body_without_replaying() -> None:
    status, body, observed = _provider_timeout_probe(header_delay=0.0, read_timeout=20.0)
    assert status == 200  # Headers already sent; the partial stream cannot be replayed.
    assert body == b""
    assert observed["body_timeout"] == 20.0
    assert observed["response_closed"] is True
    assert observed["counts"]["upstream_errors"] == 1
    assert observed["counts"]["upstream_retries"] == 0
