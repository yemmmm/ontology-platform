from __future__ import annotations

import http.client
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from modeling_team.deepseek_provider_proxy import (
    DeepSeekCredentialError,
    DeepSeekProviderProxy,
    preflight_deepseek_credential,
    read_deepseek_credential,
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
