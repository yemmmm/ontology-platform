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


def test_numeric_capture_registration_unique_requests_and_failure_do_not_change_stream(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from modeling_team.usage_capture import NumericReceiptWriter
    from modeling_team.tests.test_dsh_usage import stream

    calls = []

    class Connection:
        sock = None

        def __init__(self, *args, **kwargs):
            pass

        def request(self, method, path, body, headers):
            calls.append(1)
            # Native headers are consumed locally, never expand upstream tracing.
            assert 'x-deepseek-harness-session-id' not in headers

        def getresponse(self):
            return Response(chunks=tuple(bytes([value]) for value in stream()))

        def close(self):
            pass

    writer = NumericReceiptWriter(tmp_path / 'receipts.jsonl')
    session = MessagesProviderSession(b'test-secret', on_attempt=writer)
    session.register_usage_session('native-1', {
        'role': 'delivery', 'session_id': 'delivery-business-session',
        'process_instance': 'process-1'}, evidence_ref='dsh-baseline.jsonl')
    session.start()
    try:
        def run(native):
            return request(session, **{'x-deepseek-harness-session-id': native,
                                      'x-deepseek-harness-compact': '1'})
        with patch('modeling_team.messages_provider_proxy.http.client.HTTPSConnection', Connection):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(run, ['native-1', 'unregistered']))
            assert all(result[2] == stream() for result in results)
            # Broken collector cannot break, close or replay the model stream.
            session.on_attempt = lambda event: (_ for _ in ()).throw(OSError('PRIVATE-ERROR'))
            assert run('native-1')[2] == stream()
        assert len(calls) == 3
        session.stop()  # Close and drain the bounded numeric side channel before reading.
        rows = [json.loads(line) for line in writer.path.read_text().splitlines()]
        usage = [row for row in rows if row['event'] == 'response_usage']
        assert len(usage) == 2
        assert len({row['request_id'] for row in usage}) == 2
        bound = next(row for row in usage if row['runtime_session_id'] == 'native-1')
        assert bound['role'] == 'delivery'
        assert bound['session_id'] == 'delivery-business-session'
        assert bound['process_instance'] == 'process-1'
        assert bound['purpose'] == 'compaction'
        assert bound['usage_complete'] is True
        assert bound['raw_usage']['input_tokens'] == 40
        assert bound['raw_usage']['output_tokens'] == 20
        assert bound['raw_usage']['reasoning_tokens'] is None
        assert bound['provider_request_id'] == 'upstream-test'
        assert bound['start'] <= bound['headers_at'] <= bound['end']
        unknown = next(row for row in usage if row['runtime_session_id'] == 'unregistered')
        assert unknown.get('role') is None
        assert 'thread_id' not in bound
        assert 'PRIVATE' not in writer.path.read_text()
        assert 'test-secret' not in writer.path.read_text()
    finally:
        session.stop()


def test_blocked_collector_and_full_queue_do_not_block_requests():
    import threading
    from modeling_team.tests.test_dsh_usage import stream

    blocked = threading.Event()
    entered = threading.Event()

    def collector(event):
        entered.set()
        blocked.wait(5)

    class Connection:
        sock = None

        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return Response(chunks=[stream()])

        def close(self):
            pass

    session = MessagesProviderSession(b'test-key', on_attempt=collector)
    session.start()
    try:
        session.record_attempt({'event': 'attempt_start'})
        assert entered.wait(1)
        for index in range(1100):
            session.record_attempt({'event': 'attempt_start', 'request_id': str(index)})
        with patch('modeling_team.messages_provider_proxy.http.client.HTTPSConnection', Connection):
            assert request(session)[2] == stream()
        assert session.snapshot()['usage_capture_dropped'] > 0
        assert session._capture_queue.qsize() <= 1024
    finally:
        blocked.set()
        session.stop()


@pytest.mark.parametrize('error,reason', [
    ({'type': 'invalid_request_error', 'message': 'maximum context length exceeded PRIVATE test-secret'},
     'context_window_exceeded'),
    ({'type': 'invalid_request_error', 'message': 'tool_result must follow tool_use PRIVATE'},
     'invalid_tool_history'),
    ({'type': 'PRIVATE-TYPE', 'message': 'PRIVATE test-secret'}, 'invalid_request'),
    ({'type': ['PRIVATE-TYPE'], 'message': 'PRIVATE test-secret'}, 'invalid_request'),
])
def test_error_diagnostics_keep_safe_reason_and_request_shape_without_body(tmp_path, error, reason):
    from modeling_team.usage_capture import NumericReceiptWriter
    calls = []

    class Connection:
        sock = None

        def __init__(self, *a, **k):
            pass

        def request(self, *a, **k):
            calls.append(1)

        def getresponse(self):
            return Response(status=400, chunks=[json.dumps({'error': error}).encode()])

        def close(self):
            pass

    writer = NumericReceiptWriter(tmp_path / 'receipts.jsonl')
    session = MessagesProviderSession(b'test-secret', on_attempt=writer)
    session.start()
    payload = json.dumps({'model': 'deepseek-flash', 'max_tokens': 256000,
                         'messages': [{'role': 'user', 'content': 'PRIVATE SOURCE'}],
                         'tools': [{'name': 'PRIVATE TOOL'}]}).encode()
    try:
        with patch('modeling_team.messages_provider_proxy.http.client.HTTPSConnection', Connection):
            status, headers, body = request(session, body=payload)
        assert status == 400 and len(calls) == 1
        result = json.loads(body)
        assert result['error']['code'] == reason
        assert result['request_shape'] == {'body_bytes': len(payload), 'message_count': 1,
                                           'tool_count': 1, 'max_tokens': 256000}
        assert headers['x-request-id'] == 'upstream-test'
        session.stop()
        evidence = writer.path.read_text()
        assert 'PRIVATE' not in evidence + body.decode()
        assert 'test-secret' not in evidence + body.decode()
        usage = next(json.loads(row) for row in evidence.splitlines()
                     if json.loads(row)['event'] == 'response_usage')
        assert usage['provider_error']['reason_code'] == reason
        assert usage['request_shape'] == result['request_shape']
    finally:
        session.stop()


@pytest.mark.parametrize('chunks,broken', [
    ([b'not-json PRIVATE'], False), ([b'x' * 10000], False), ([], True),
])
def test_unreadable_or_large_error_body_preserves_original_status_without_replay(chunks, broken):
    class Connection:
        sock = None

        def __init__(self, *a, **k):
            pass

        def request(self, *a, **k):
            pass

        def getresponse(self):
            return Response(status=400, chunks=chunks, broken=broken)

        def close(self):
            pass

    session = MessagesProviderSession(b'test-secret')
    session.start()
    try:
        with patch('modeling_team.messages_provider_proxy.http.client.HTTPSConnection', Connection):
            status, _, body = request(session)
        assert status == 400
        assert json.loads(body)['error']['code'] == 'invalid_request'
        assert b'PRIVATE' not in body and len(body) < 1000
    finally:
        session.stop()
