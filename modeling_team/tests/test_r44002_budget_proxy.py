"""Budget checks at real local provider handlers; no external HTTP requests."""

import io
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from modeling_team.deepseek_provider_proxy import ResponsesProviderSession, _SessionHandler
from modeling_team.messages_provider_proxy import MessagesProviderSession
from modeling_team.task_budget import TaskBudget
from modeling_team.tests.test_messages_provider_proxy import request
from modeling_team.usage_capture import NumericReceiptWriter


def _budget(tmp_path, amount="1"):
    return TaskBudget.create(tmp_path / "cost-budget", {
        "task_ref": "proxy-task", "authorization_reference": "user-fixture",
        "amount": amount,
        "prices": [{
            "provider": "deepseek-direct", "actual_model": "model-a",
            "cached_input_per_million": "0.2", "uncached_input_per_million": "2",
            "output_per_million": "8",
        }, {
            "provider": "glm-messages", "actual_model": "glm-5.3-flash",
            "cached_input_per_million": "0.2", "uncached_input_per_million": "2",
            "output_per_million": "8",
        }],
    })


def _handler(session, payload=None):
    handler = object.__new__(_SessionHandler)
    body = json.dumps(payload or {"model": "model-a", "input": "private-business"}).encode()
    handler.server = type("Server", (), {"session": session})()
    handler.path = "/responses"
    handler.headers = {"Content-Length": str(len(body)), "Content-Type": "application/json"}
    handler.rfile, handler.wfile = io.BytesIO(body), io.BytesIO()
    handler.response_statuses = []
    handler.send_response = handler.response_statuses.append
    handler.send_header = lambda *args: None
    handler.end_headers = lambda: None
    handler._client_disconnected = lambda: False
    return handler


def _admission(budget, observed):
    def before_request(receipt):
        observed.append(receipt)
        budget.require_available(binding={
            "provider": receipt["provider"], "actual_model": receipt["requested_model"],
        })
    return before_request


def test_zero_budget_never_forwards_or_invents_usage(tmp_path):
    budget = _budget(tmp_path, "0")
    path = tmp_path / "provider.jsonl"
    writer = NumericReceiptWriter(path, {"key_ref": "fixture-credential"})
    budget.register_source("proxy", path, "capture")
    observed = []
    session = ResponsesProviderSession(b"fixture", before_request=_admission(budget, observed),
                                      on_attempt=writer)
    handler = _handler(session)
    with patch.object(session, "forward") as forward:
        handler.do_POST()
    forward.assert_not_called()
    assert handler.response_statuses == [402]
    row = json.loads(path.read_text())
    assert row["status"] == "not_admitted"
    assert "usage" not in row and "raw_usage" not in row
    state = budget.tick(now=datetime.now(timezone.utc) + timedelta(seconds=11))
    assert state["pending_settlement"] == 0
    assert state["inflight_count"] == 0
    assert session.snapshot()["upstream_errors"] == 0
    assert len(observed) == 1


def test_each_automatic_retry_rechecks_shared_task_budget(tmp_path):
    budget = _budget(tmp_path, "0.48")
    path = tmp_path / "provider.jsonl"
    writer = NumericReceiptWriter(path, {"key_ref": "fixture-credential"})
    budget.register_source("proxy", path, "capture")
    observed = []
    session = ResponsesProviderSession(b"fixture", before_request=_admission(budget, observed),
                                      on_attempt=writer, retry_backoff_seconds=(0,))
    handler = _handler(session)

    def first_attempt(_body):
        writer({
            **observed[0], "event": "response_usage", "response_id": "paid-attempt",
            "status": "completed", "actual_model": "model-a",
            "raw_usage": {"input_tokens": 200_000, "output_tokens": 10_000},
            "present_fields": ["input_tokens", "output_tokens"],
            "usage_complete": True,
        })
        assert budget.tick()["charged_estimate"] == "0.48"
        return 429, {}, io.BytesIO(b"private-provider-text")

    with patch.object(session, "forward", side_effect=first_attempt) as forward:
        handler.do_POST()
    assert forward.call_count == 1
    assert [row["attempt_index"] for row in observed] == [1, 2]
    assert handler.response_statuses == [402]
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert rows[-1]["status"] == "not_admitted"
    assert rows[-1]["attempt_index"] == 2
    assert "private" not in str(rows)
    assert budget.tick()["charged_estimate"] == "0.48"


def test_glm_budget_refusal_never_opens_upstream_or_observer(tmp_path):
    budget = _budget(tmp_path, "0")
    observed, rows = [], []
    session = MessagesProviderSession(
        b"fixture", provider_id="glm-messages",
        before_request=_admission(budget, observed), on_attempt=rows.append,
    )
    session.start()
    try:
        with patch("modeling_team.messages_provider_proxy.http.client.HTTPSConnection") as upstream, \
             patch("modeling_team.messages_provider_proxy.MessagesUsageObserver") as observer:
            code, _, body = request(session, body=b'{"model":"glm-5.3-flash","stream":true}')
        assert (code, body) == (402, b"")
        upstream.assert_not_called()
        observer.assert_not_called()
        assert len(observed) == 1
    finally:
        session.stop()
    assert len(rows) == 1 and rows[0]["status"] == "not_admitted"


@pytest.mark.parametrize("native_input", [False, True])
def test_exact_host_control_is_admitted_once_without_lending_it_to_retries(tmp_path, native_input):
    budget = _budget(tmp_path, "0")
    control_id, text = "member-a:pause:1", '{"action":"pause","request_id":"member-a:1"}'
    budget.require_available(control_id=control_id)
    observed = []

    def admit(receipt):
        observed.append(receipt)
        if receipt.get("_budget_control_admitted") is not True:
            budget.require_available()

    session = ResponsesProviderSession(b"fixture", before_request=admit,
                                      retry_backoff_seconds=(0,))
    session.authorize_control(text, control_id)
    # An older control in history does not let an ordinary new request borrow
    # the one current Host allowance.
    wrong = _handler(session, {"model": "model-a", "input": [
        {"role": "user", "content": text}, {"role": "assistant", "content": "continued"},
    ]})
    with patch.object(session, "forward") as forward:
        wrong.do_POST()
    forward.assert_not_called()
    assert wrong.response_statuses == [402]
    inputs = ([{"role": "user", "content": [{"type": "input_text", "text": text}]}]
              if native_input else text)
    control = _handler(session, {"model": "model-a", "input": inputs})
    with patch.object(session, "forward", return_value=(429, {}, io.BytesIO(b"discard"))) as forward:
        control.do_POST()
    assert forward.call_count == 1
    assert control.response_statuses == [402]  # the automatic retry was denied
    grants = [row for row in observed if row.get("_budget_control_admitted") is True]
    assert len(grants) == 1 and grants[0]["_budget_control_id"] == control_id


def test_verified_credential_reference_is_stable_and_contains_no_path_or_key(tmp_path):
    import os
    from modeling_team.deepseek_provider_proxy import preflight_deepseek_credential

    path = tmp_path / "private-provider.env"
    path.write_text("DEEPSEEK_API_KEY=fixture-secret-value\n")
    path.chmod(0o600)
    first = preflight_deepseek_credential(path)
    assert preflight_deepseek_credential(path).key_ref == first.key_ref
    assert first.key_ref.startswith("credential-binding:")
    assert "fixture" not in first.key_ref and str(path) not in first.key_ref
    os.utime(path, ns=(path.stat().st_atime_ns, first.st_mtime_ns + 1))
    assert preflight_deepseek_credential(path).key_ref != first.key_ref


@pytest.mark.parametrize("rebuilt", [False, True])
def test_provider_manager_preserves_request_gate_on_start_and_recovery(monkeypatch, rebuilt):
    from modeling_team import model_routing

    admitted = []
    sessions = []

    class Session:
        bound_port = 44002
        def __init__(self, _credential, **kwargs):
            self.hook = kwargs["before_request"]
            self.listening = True
            sessions.append(self)
        def start(self):
            pass
        def stop(self):
            return True
        def snapshot(self):
            return {"listening": self.listening}

    monkeypatch.setattr(model_routing, "_PROVIDER_CREDENTIAL_READERS", {
        **model_routing._PROVIDER_CREDENTIAL_READERS, "deepseek-direct": lambda _: b"fixture",
    })
    manager = model_routing.ProviderSessionManager(
        {"deepseek-direct": object()}, session_factory=Session, before_request=admitted.append,
    )
    manager.start()
    if rebuilt:
        sessions[0].listening = False
        assert manager.restart_dead_sessions()["deepseek-direct"] is True
    sessions[-1].hook({"attempt_index": 1})
    assert admitted == [{"attempt_index": 1}]
