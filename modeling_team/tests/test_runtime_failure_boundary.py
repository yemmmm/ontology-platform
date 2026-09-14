from __future__ import annotations

import json
import os
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from modeling_team.runner import TeamRunner
from modeling_team.runtimes.codex import (
    CodexRuntimeAdapter,
    CodexRuntimeRPCError,
    _Agent,
)


def _agent(tmp_path: Path, *, active: str = "turn-1") -> _Agent:
    return _Agent(
        "protocol",
        SimpleNamespace(role="protocol"),
        tmp_path / "home",
        tmp_path / "work",
        tmp_path / "skills",
        thread_id="thread-1",
        active_turn_id=active,
        state="running",
    )


def _error_notification(
    *,
    will_retry: bool,
    turn_id: str = "turn-1",
    info: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "method": "error",
        "params": {
            "threadId": "thread-1",
            "turnId": turn_id,
            "willRetry": will_retry,
            "error": {
                "message": "provider text must never be retained",
                "codexErrorInfo": info
                if info is not None
                else {"responseStreamConnectionFailed": {"httpStatusCode": 503}},
                "additionalDetails": "provider details must never be retained",
            },
        },
    }


def test_retryable_provider_error_is_sanitized_and_does_not_refresh_progress(tmp_path: Path) -> None:
    adapter = CodexRuntimeAdapter(repository_root=tmp_path)
    adapter._run_root = tmp_path
    agent = _agent(tmp_path)
    adapter.agents[agent.agent_id] = agent
    agent.last_output_monotonic = 123.0

    adapter._notification(agent, _error_notification(will_retry=True))

    assert agent.runtime_failure is None
    assert adapter.consume_runtime_failures() == []
    assert agent.last_output_monotonic == 123.0
    evidence = (tmp_path / "evidence" / "provider-error.jsonl").read_text()
    assert "provider text" not in evidence
    assert "provider details" not in evidence
    assert "responseStreamConnectionFailed" in evidence
    assert '"http_status": 503' in evidence


def test_terminal_provider_error_latches_once_and_secondary_eof_is_ignored(tmp_path: Path) -> None:
    adapter = CodexRuntimeAdapter(repository_root=tmp_path)
    adapter._run_root = tmp_path
    read_fd, write_fd = os.pipe()
    os.close(write_fd)
    output = os.fdopen(read_fd, "rb", buffering=0)
    process = SimpleNamespace(stdin=StringIO(), stdout=output, pid=None, terminate=lambda: None)
    agent = _agent(tmp_path)
    agent.process = process
    adapter.agents[agent.agent_id] = agent
    try:
        # misalignmentPolicyViolation is not externally recoverable, so an
        # exhausted SDK retry keeps the fatal latch.
        adapter._notification(
            agent,
            _error_notification(
                will_retry=False,
                info="misalignmentPolicyViolation",
            ),
        )
        assert agent.state == "failed"
        failures = adapter.consume_runtime_failures()
        assert len(failures) == 1
        assert failures[0][1]["reason"] == "provider-error-terminal"
        assert adapter.consume_runtime_failures() == []
        # Process termination closes stdout asynchronously; the typed failure is
        # still the sole cause exposed to the caller.
        assert adapter.receive_messages() == []
        assert "provider text" not in repr(failures)
    finally:
        output.close()


@pytest.mark.parametrize(
    "bad",
    [
        {"willRetry": "false"},
        {"willRetry": False, "error": {"message": 3}},
        {"willRetry": False, "error": {"message": "x", "codexErrorInfo": {"unknown": {}}}},
        {"willRetry": False, "error": {"message": "x", "codexErrorInfo": {"responseStreamConnectionFailed": {"httpStatusCode": 65536}}}},
    ],
)
def test_malformed_provider_error_latches_without_provider_text(tmp_path: Path, bad: dict[str, object]) -> None:
    adapter = CodexRuntimeAdapter(repository_root=tmp_path)
    adapter._run_root = tmp_path
    agent = _agent(tmp_path)
    adapter.agents[agent.agent_id] = agent
    params: dict[str, object] = {
        "threadId": "thread-1",
        "turnId": "turn-1",
        **bad,
    }
    adapter._notification(agent, {"method": "error", "params": params})
    assert agent.runtime_failure is not None
    assert agent.runtime_failure["reason"] == "provider-error-malformed"
    assert adapter.consume_runtime_failures()[0][1]["variant"] == "malformed"


def _current_protocol_turn_error(
    *, will_retry: bool = True, **error_overrides: object
) -> dict[str, object]:
    """TurnError exactly as codex-cli 0.153.4 serializes it.

    Field set and nullability come from ``codex app-server generate-ts``
    (``TurnError.ts``): ``misalignment`` has no ``skip_serializing_if``, so it is
    present on every notification, null unless the provider blocked on
    misalignment grounds.
    """

    error: dict[str, object] = {
        "message": "provider text must never be retained",
        "codexErrorInfo": {"responseStreamConnectionFailed": {"httpStatusCode": 503}},
        "additionalDetails": None,
        "misalignment": None,
    }
    error.update(error_overrides)
    return {
        "method": "error",
        "params": {
            "threadId": "thread-1",
            "turnId": "turn-1",
            "willRetry": will_retry,
            "error": error,
        },
    }


@pytest.mark.parametrize(
    "error_overrides",
    [
        {},
        # codex-cli serializes this on every notification; null unless the
        # provider blocked on misalignment grounds.
        {"misalignment": None},
        # Unused provider-authored metadata: neither interpreted nor retained,
        # so it must not kill a retryable notification.
        {
            "misalignment": {
                "errorType": "canary-classification",
                "detailedExplanation": "canary explanation text",
                "steer": {"message": "canary steer text"},
            },
            "futureField": "canary future metadata",
        },
    ],
)
def test_current_protocol_error_notification_is_retryable_not_malformed(
    tmp_path: Path, error_overrides: dict[str, object]
) -> None:
    """Legal nullable/unused ``TurnError`` metadata must not latch a run failure."""

    adapter = CodexRuntimeAdapter(repository_root=tmp_path)
    adapter._run_root = tmp_path
    agent = _agent(tmp_path)
    adapter.agents[agent.agent_id] = agent
    agent.last_output_monotonic = 123.0

    adapter._notification(agent, _current_protocol_turn_error(**error_overrides))

    assert agent.runtime_failure is None
    assert adapter.consume_runtime_failures() == []
    assert agent.last_output_monotonic == 123.0
    evidence = (tmp_path / "evidence" / "provider-error.jsonl").read_text()
    assert "provider text" not in evidence
    for canary in ("canary-classification", "canary explanation text", "canary steer text", "canary future metadata"):
        assert canary not in evidence
    assert "responseStreamConnectionFailed" in evidence


@pytest.mark.parametrize(
    "variant",
    ["rateLimitExceeded", "misalignmentPolicyViolation"],
)
def test_current_protocol_error_info_variants_are_classified(tmp_path: Path, variant: str) -> None:
    adapter = CodexRuntimeAdapter(repository_root=tmp_path)
    adapter._run_root = tmp_path
    agent = _agent(tmp_path)
    adapter.agents[agent.agent_id] = agent

    adapter._notification(
        agent,
        _current_protocol_turn_error(codexErrorInfo=variant),
    )

    assert agent.runtime_failure is None
    evidence = (tmp_path / "evidence" / "provider-error.jsonl").read_text()
    assert f'"variant": "{variant}"' in evidence


def test_current_protocol_terminal_error_still_latches(tmp_path: Path) -> None:
    adapter = CodexRuntimeAdapter(repository_root=tmp_path)
    adapter._run_root = tmp_path
    agent = _agent(tmp_path)
    adapter.agents[agent.agent_id] = agent

    adapter._notification(
        agent,
        _current_protocol_turn_error(
            will_retry=False,
            codexErrorInfo="misalignmentPolicyViolation",
            misalignment={"errorType": "canary-classification", "steer": {"message": "canary steer text"}},
        ),
    )

    assert agent.state == "failed"
    failures = adapter.consume_runtime_failures()
    assert failures[0][1]["reason"] == "provider-error-terminal"
    assert failures[0][1]["will_retry"] is False
    evidence = (tmp_path / "evidence" / "runtime-failure.jsonl").read_text()
    assert "canary" not in evidence
    assert "provider text" not in evidence


@pytest.mark.parametrize(
    "params_override,variant",
    [
        ({"threadId": "thread-other"}, "thread-mismatch"),
        ({"turnId": "turn-other"}, "turn-mismatch"),
    ],
)
def test_ownership_mismatch_still_latches(
    tmp_path: Path, params_override: dict[str, object], variant: str
) -> None:
    adapter = CodexRuntimeAdapter(repository_root=tmp_path)
    adapter._run_root = tmp_path
    agent = _agent(tmp_path)
    adapter.agents[agent.agent_id] = agent

    notification = _current_protocol_turn_error(will_retry=False)
    notification["params"].update(params_override)
    adapter._notification(agent, notification)

    assert agent.runtime_failure["reason"] == "provider-error-malformed"
    assert adapter.consume_runtime_failures()[0][1]["variant"] == variant


def test_progress_clock_uses_explicit_allowlist(tmp_path: Path) -> None:
    adapter = CodexRuntimeAdapter(repository_root=tmp_path)
    agent = _agent(tmp_path)
    agent.last_output_monotonic = 321.0
    adapter._notification(agent, {"method": "thread/status/changed", "params": {}})
    assert agent.last_output_monotonic == 321.0
    adapter._notification(
        agent,
        {"method": "item/agentMessage/delta", "params": {"itemId": "i", "delta": "x"}},
    )
    assert agent.last_output_monotonic > 321.0


def test_jsonrpc_error_is_typed_and_keeps_sanitized_message_without_data(tmp_path: Path) -> None:
    adapter = CodexRuntimeAdapter(repository_root=tmp_path)
    read_fd, write_fd = os.pipe()
    output = os.fdopen(read_fd, "rb", buffering=0)
    process = SimpleNamespace(stdin=StringIO(), stdout=output)
    agent = _agent(tmp_path)
    agent.process = process
    try:
        os.write(
            write_fd,
            (
                json.dumps(
                    {
                        "id": 1,
                        "error": {
                            "code": -32001,
                            "message": "provider secret message",
                            "data": {"token": "secret-token"},
                        },
                    }
                )
                + "\n"
            ).encode(),
        )
        with pytest.raises(CodexRuntimeRPCError) as raised:
            adapter._rpc(agent, "turn/steer", {})
        error = raised.value
        assert (error.method, error.code, error.category) == ("turn/steer", -32001, "rpc_error")
        # R2.3-008 start3 diagnosability: the server-generated ``message`` text is
        # retained (sanitized) so a fatal -32603 carries its cause; only the
        # provider-controlled ``data`` payload stays discarded.
        assert error.server_message == "provider secret message"
        assert "provider secret message" in str(error)
        assert "secret-token" not in repr(error)
    finally:
        os.close(write_fd)
        output.close()


def test_jsonrpc_error_message_is_sanitized_and_bounded() -> None:
    error = CodexRuntimeAdapter._rpc_error_from_value(
        "thread/start",
        {"code": -32603, "message": "internal error:\n  cause\twith  control   chars\n"},
    )
    assert error.server_message == "internal error: cause with control chars"
    long_error = CodexRuntimeAdapter._rpc_error_from_value(
        "thread/start", {"code": -32603, "message": "x" * 500}
    )
    assert long_error.server_message == "x" * 240
    malformed = CodexRuntimeAdapter._rpc_error_from_value(
        "thread/start", {"code": -32603, "message": 7}
    )
    assert malformed.category == "malformed_rpc_error"
    assert malformed.server_message is None
    assert "message" not in str(malformed)


def test_runner_runtime_failure_finalizer_is_exactly_once(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir()
    runner = TeamRunner(repository_root=tmp_path, adapter=SimpleNamespace())
    runner.run = SimpleNamespace(root=tmp_path, run_id="run-runtime-failure")
    runner.record_terminal_failure = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
    runner.cleanup = lambda: {"runtime": {"private_credentials_destroyed": True}}  # type: ignore[method-assign]
    first = runner._finalize_runtime_failure(
        [("protocol", {"role": "protocol", "reason": "provider-error-terminal"})]
    )
    second = runner._finalize_runtime_failure(
        [("protocol", {"role": "protocol", "reason": "provider-error-terminal"})]
    )
    assert first[0]["type"] == "runtime-failure"
    assert second == []
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["state"] == "TERMINAL_REPORT_COMPLETE"
    assert len((tmp_path / "evidence" / "runtime-failure.jsonl").read_text().splitlines()) == 1
