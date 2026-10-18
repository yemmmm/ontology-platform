"""Collection cannot alter runtime behavior or expose request content."""

import json


from modeling_team.usage_capture import NumericReceiptWriter
from modeling_team.tests.test_delivery_runtime import ROOT, _runtime
from modeling_team.model_routing import load_team_model_profile
from modeling_team.runtimes import delivery as delivery_module
from modeling_team.runtimes.codex import CodexRuntimeAdapter


def test_numeric_whitelist_duplicate_notifications_and_failure(tmp_path, caplog):
    writer = NumericReceiptWriter(
        tmp_path / "usage.jsonl",
        {"session_id": "session", "role": "business-answerer", "secret": "DO_NOT_STORE"},
    )
    event = dict(
        event="thread_usage",
        thread_id="thread",
        turn_id="turn",
        total=dict(inputTokens=100, outputTokens=20, cachedInputTokens=110),
        body="DO_NOT_STORE",
        headers="DO_NOT_STORE",
        error="DO_NOT_STORE",
    )
    writer(event)
    writer(event)
    rows = [json.loads(line) for line in writer.path.read_text().splitlines()]
    assert len(rows) == 2
    assert rows[0]["total"]["input_tokens"] == 100
    assert rows[0]["total"]["cached_input_tokens"] is None
    assert rows[0]["total"]["reasoning_output_tokens"] is None
    assert rows[0]["invalid_fields"] == ["cached_input_tokens"]
    assert "DO_NOT_STORE" not in writer.path.read_text()
    assert writer.path.stat().st_mode & 0o777 == 0o600
    broken = NumericReceiptWriter(tmp_path / "usage.jsonl" / "child")
    broken(event)
    assert "usage_capture_incomplete" in caplog.text
    assert "DO_NOT_STORE" not in caplog.text


def test_delivery_usage_does_not_enter_observations_or_change_turn(tmp_path, caplog):
    runtime = _runtime(
        delivery_module,
        load_team_model_profile(ROOT, "openai-sol-medium"),
        tmp_path / "native",
        usage_context={
            "role": "business-answerer",
            "operation_id": "answer-operation",
            "session_id": "session",
        },
    )
    value = {
        "method": "thread/tokenUsage/updated",
        "params": {
            "threadId": "thread",
            "turnId": "turn",
            "business": "DO_NOT_STORE",
            "tokenUsage": {"total": {"inputTokens": 100, "outputTokens": 20}},
        },
    }
    runtime.busy = True
    runtime._handle(value)
    row = json.loads((runtime.home / "usage-events.jsonl").read_text())
    assert row["role"] == "business-answerer"
    assert row["operation_id"] == "answer-operation"
    assert row["requested_model"] == runtime.binding.model
    assert runtime.busy is True
    assert runtime._observations == []
    runtime._usage_writer = lambda _event: (_ for _ in ()).throw(RuntimeError("DO_NOT_STORE"))
    runtime._handle(value)
    assert runtime.busy is True
    assert caplog.messages[-1] == "usage_capture_incomplete"


def test_codex_production_and_standalone_keep_numeric_attempt_receipts(tmp_path):
    runtime = CodexRuntimeAdapter(repository_root=tmp_path)
    event = {
        "event": "attempt_start",
        "request_id": "req",
        "attempt_index": 1,
        "status": "unfinished",
        "provider": "provider",
        "body": "DO_NOT_STORE",
    }
    runtime._record_provider_attempt(event)
    paths = list((tmp_path / "workspaces" / "usage-receipts").rglob("provider-attempts.jsonl"))
    assert len(paths) == 1
    assert json.loads(paths[0].read_text())["run_id"] is None
    runtime._run_root = tmp_path / "run"
    runtime._run_id = "run-id"
    runtime._record_provider_attempt(event)
    row = json.loads((runtime._run_root / "evidence" / "provider-attempts.jsonl").read_text())
    assert row["run_id"] == "run-id"
    assert "DO_NOT_STORE" not in json.dumps(row)


def test_resumed_numeric_file_and_directory_remain_private(tmp_path):
    parent = tmp_path / 'previous-evidence'
    parent.mkdir(mode=0o755)
    target = parent / 'dsh-provider.jsonl'
    target.write_text('')
    target.chmod(0o644)
    NumericReceiptWriter(target)({'event': 'attempt_start', 'request_id': 'single-request'})
    assert target.stat().st_mode & 0o777 == 0o600
    assert parent.stat().st_mode & 0o777 == 0o700
