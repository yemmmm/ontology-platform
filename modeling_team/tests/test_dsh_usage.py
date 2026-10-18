"""034 numeric receipts: exact bytes and deterministic offline accounting only."""

import json

import pytest

from modeling_team.dsh_usage import MessagesUsageObserver, normalize_dsh_usage


def event(kind, **values):
    return (
        "event: "
        + kind
        + "\r\ndata: "
        + json.dumps(dict(type=kind, **values), ensure_ascii=False)
        + "\r\n\r\n"
    ).encode()


def stream():
    return (
        event(
            "message_start",
            message=dict(
                id="msg-1",
                model="deepseek-flash",
                usage=dict(
                    input_tokens=40,
                    cache_read_input_tokens=60,
                    cache_creation_input_tokens=5,
                    output_tokens=0,
                ),
            ),
        )
        + event("content_block_delta", delta={"text": "PRIVATE-正文"})
        + event("message_delta", usage={"output_tokens": 20})
        + event("message_stop")
    )


def test_every_byte_boundary_presence_final_output_and_no_content():
    raw = stream()
    for size in (1, 2, 7, len(raw)):
        observer = MessagesUsageObserver()
        for start in range(0, len(raw), size):
            observer.feed(raw[start : start + size])
        result = observer.finish()
        assert result["response_id"] == "msg-1"
        assert result["raw_usage"]["output_tokens"] == 20
        assert result["usage_complete"] is True
        assert "PRIVATE" not in json.dumps(result)
        usage, invalid = normalize_dsh_usage(result["raw_usage"], "messages")
        assert not invalid
        assert usage["input_tokens"] == 105
        assert usage["cached_input_tokens"] == 60
        assert usage["cache_write_tokens"] == 5
        assert usage["reasoning_output_tokens"] is None


@pytest.mark.parametrize("suffix", [b"", event("message_stop")])
def test_initial_output_zero_is_not_final(suffix):
    observer = MessagesUsageObserver()
    observer.feed(event("message_start", message={"usage": {"output_tokens": 0}}) + suffix)
    result = observer.finish()
    assert not result["usage_complete"]
    assert result["raw_usage"]["output_tokens"] is None
    assert "output_tokens" in result["present_fields"]


def test_bounded_bad_frames_decreasing_values_and_missing_buckets():
    observer = MessagesUsageObserver(max_event_bytes=4096)
    observer.feed(event("message_delta", usage={"output_tokens": 20}))
    observer.feed(event("message_delta", usage={"output_tokens": 10}))
    observer.feed(event("message_stop"))
    result = observer.finish()
    assert "usage_decreased:output_tokens" in result["usage_issues"]
    assert result["raw_usage"]["output_tokens"] is None
    observer = MessagesUsageObserver(max_event_bytes=32)
    observer.feed(b"data: " + b"x" * 100000)
    assert len(observer.buffer) <= 32
    assert "event_too_large" in observer.finish()["usage_issues"]
    usage, invalid = normalize_dsh_usage(
        {"input_tokens": 40, "cache_read_input_tokens": 60}, "messages"
    )
    assert usage["input_tokens"] is None
    assert usage["cached_input_tokens"] == 60
    assert not invalid


def test_invalid_boolean_and_reasoning_subset():
    usage, invalid = normalize_dsh_usage(
        dict(
            inputTokens=True,
            cacheReadTokens=0,
            cacheWriteTokens=0,
            outputTokens=3,
            reasoningTokens=4,
        ),
        "native",
    )
    assert usage["input_tokens"] is None
    assert usage["reasoning_output_tokens"] is None
    assert len(invalid) == 2


def test_multiline_data_invalid_utf8_and_input_position():
    observer = MessagesUsageObserver()
    observer.feed(b'data: {"type":"message_start",\r\ndata: "message":{"usage":{}}}\r\n\r\n')
    observer.feed(b"data: \xff\n\n")
    observer.feed(event("message_delta", usage={"input_tokens": 40, "output_tokens": 0}))
    observer.feed(event("message_stop"))
    result = observer.finish()
    assert "invalid_sse_event" in result["usage_issues"]
    assert "input_outside_start:input_tokens" in result["usage_issues"]
    assert "message_start_missing" not in result["usage_issues"]
    assert result["raw_usage"]["input_tokens"] is None
    assert result["raw_usage"]["output_tokens"] == 0
