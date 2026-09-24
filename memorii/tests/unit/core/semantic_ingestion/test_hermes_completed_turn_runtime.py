from __future__ import annotations

import queue
import threading

import pytest
from memorii.core.semantic_ingestion.hermes_completed_turn_runtime import (
    HermesCompletedTurnRuntime,
    _canonical_messages_digest,
    _canonicalize_completed_messages,
    _CompletedTurnWork,
)


def _worker_runtime() -> HermesCompletedTurnRuntime:
    """Construct only the isolated worker boundary used by recovery tests."""
    runtime = object.__new__(HermesCompletedTurnRuntime)
    runtime._work = queue.Queue()
    runtime._condition = threading.Condition()
    runtime._outstanding = 0
    runtime._failures = []
    runtime._worker = threading.Thread(target=runtime._worker_loop, daemon=True)
    runtime._worker.start()
    return runtime


def test_post_admission_failure_recovers_before_idle_and_clears_failure() -> None:
    runtime = _worker_runtime()
    process_calls: list[object] = []
    recovery_calls: list[str] = []

    def fail_once(work: object) -> None:
        process_calls.append(work)
        raise RuntimeError("post-admission failure")

    runtime._process = fail_once
    runtime._recover_pending = lambda: recovery_calls.append("recovered")
    runtime._enqueue(_CompletedTurnWork(admitted=object(), ingress=object()))

    runtime.wait_for_idle(timeout=1.0)

    assert len(process_calls) == 1
    assert recovery_calls == ["recovered"]
    assert runtime._failures == []


def test_persistent_recovery_failure_remains_visible_without_rescheduling() -> None:
    runtime = _worker_runtime()
    recovery_calls: list[str] = []
    runtime._process = lambda _work: (_ for _ in ()).throw(RuntimeError("post-admission failure"))

    def failed_recovery() -> None:
        recovery_calls.append("attempted")
        raise RuntimeError("recovery remained pending")

    runtime._recover_pending = failed_recovery
    runtime._enqueue(_CompletedTurnWork(admitted=object(), ingress=object()))

    with pytest.raises(RuntimeError, match="semantic worker failed") as first:
        runtime.wait_for_idle(timeout=1.0)
    with pytest.raises(RuntimeError, match="semantic worker failed") as second:
        runtime.wait_for_idle(timeout=1.0)

    assert first.value.__cause__ is second.value.__cause__
    assert recovery_calls == ["attempted"]
    assert len(runtime._failures) == 2
    assert runtime._work.empty()


def test_full_transcript_canonicalization_accepts_matched_tool_sequence() -> None:
    messages = _canonicalize_completed_messages(
        messages=[
            {"role": "user", "content": "Find Atlas"},
            {"role": "assistant", "content": "Calling lookup.", "tool_calls": [{
                "id": "call-1", "type": "function",
                "function": {"name": "lookup", "arguments": "{\"name\":\"Atlas\"}"},
            }]},
            {"role": "tool", "content": "Atlas found", "tool_call_id": "call-1"},
            {"role": "assistant", "content": "Atlas is found."},
        ],
        user_content="Find Atlas",
        assistant_content="Atlas is found.",
    )

    assert messages[-1] == {"role": "assistant", "content": "Atlas is found."}


def test_full_transcript_canonicalization_discards_known_hermes_message_carriers() -> None:
    messages = _canonicalize_completed_messages(
        messages=[
            {
                "role": "user",
                "content": "Find Atlas",
                "timestamp": "2026-09-24T00:00:00Z",
                "display_kind": "user",
                "display_metadata": {"channel": "cli"},
                "platform_message_id": "platform:user:1",
                "api_content": [{"type": "input_text", "text": "Find Atlas"}],
                "_db_persisted": True,
                "_row_id": 41,
            },
            {
                "role": "assistant",
                "content": "Atlas is found.",
                "reasoning": "private",
                "finish_reason": "stop",
                "timestamp": "2026-09-24T00:00:01Z",
                "reasoning_content": "private",
                "reasoning_details": [{"type": "summary"}],
                "anthropic_content_blocks": [],
                "bedrock_content_blocks": [],
                "codex_reasoning_items": [],
                "codex_message_items": [],
                "api_content": [{"type": "output_text", "text": "Atlas is found."}],
                "_db_persisted": True,
                "_row_id": 42,
            },
        ],
        user_content="Find Atlas",
        assistant_content="Atlas is found.",
    )

    assert messages == (
        {"role": "user", "content": "Find Atlas", "timestamp": "2026-09-24T00:00:00Z"},
        {"role": "assistant", "content": "Atlas is found.", "timestamp": "2026-09-24T00:00:01Z"},
    )


def test_full_transcript_canonicalization_accepts_decorated_tool_sequence() -> None:
    messages = _canonicalize_completed_messages(
        messages=[
            {"role": "user", "content": "Find Atlas", "timestamp": "2026-09-24T00:00:00Z"},
            {
                "role": "assistant",
                "content": "Calling lookup.",
                "reasoning": "private",
                "tool_calls": [{
                    "id": "call-1", "type": "function",
                    "function": {"name": "lookup", "arguments": "{\"name\":\"Atlas\"}"},
                }],
            },
            {
                "role": "tool",
                "content": "Atlas found",
                "tool_call_id": "call-1",
                "name": "lookup",
                "tool_name": "lookup",
                "timestamp": "2026-09-24T00:00:01Z",
                "_tool_output_risk": "low",
                "effect_disposition": "read_only",
            },
            {"role": "assistant", "content": "Atlas is found.", "finish_reason": "stop"},
        ],
        user_content="Find Atlas",
        assistant_content="Atlas is found.",
    )

    assert messages[1]["tool_calls"] == (
        {"id": "call-1", "type": "function", "name": "lookup", "arguments": "{\"name\":\"Atlas\"}"},
    )
    assert messages[2] == {
        "role": "tool",
        "content": "Atlas found",
        "tool_call_id": "call-1",
        "timestamp": "2026-09-24T00:00:01Z",
    }


@pytest.mark.parametrize("timestamp", [None, "not-a-timestamp", "2026-09-24T00:00:00"])
def test_completed_turn_timestamp_requires_a_timezone_aware_final_persisted_timestamp(timestamp: object) -> None:
    final: dict[str, object] = {"role": "assistant", "content": "Acknowledged."}
    if timestamp is not None:
        final["timestamp"] = timestamp

    from memorii.core.semantic_ingestion.hermes_completed_turn_runtime import _completed_turn_timestamp

    with pytest.raises(ValueError, match="timestamp"):
        canonical = _canonicalize_completed_messages(
            messages=[
                {"role": "user", "content": "Remember Atlas", "timestamp": "2026-09-24T00:00:00Z"},
                final,
            ],
            user_content="Remember Atlas",
            assistant_content="Acknowledged.",
        )
        _completed_turn_timestamp(canonical)


def test_full_transcript_canonicalization_accepts_real_hermes_textless_tool_call() -> None:
    messages = _canonicalize_completed_messages(
        messages=[
            {"role": "user", "content": "Find Atlas", "timestamp": "2026-09-24T00:00:00Z"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": "tool-call:1",
                    "call_id": "provider-call:1",
                    "response_item_id": "response-item:1",
                    "type": "function",
                    "function": {"name": "lookup", "arguments": "{\"name\":\"Atlas\"}"},
                    "extra_content": {"provider": "hermes"},
                }],
            },
            {"role": "tool", "content": "Atlas found", "tool_call_id": "tool-call:1"},
            {"role": "assistant", "content": "Atlas is found."},
        ],
        user_content="Find Atlas",
        assistant_content="Atlas is found.",
    )

    assert messages[1] == {
        "role": "assistant",
        "content": "",
        "tool_calls": (
            {"id": "tool-call:1", "type": "function", "name": "lookup", "arguments": "{\"name\":\"Atlas\"}"},
        ),
    }


def test_tool_arguments_are_json_canonicalized_for_equivalent_transport_encodings() -> None:
    def transcript(arguments: str) -> tuple[dict[str, object], ...]:
        return _canonicalize_completed_messages(
            messages=[
                {"role": "user", "content": "Find Atlas"},
                {
                    "role": "assistant",
                    "content": "Calling lookup.",
                    "tool_calls": [{
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "lookup", "arguments": arguments},
                    }],
                },
                {"role": "tool", "content": "Atlas found", "tool_call_id": "call-1"},
                {"role": "assistant", "content": "Atlas is found."},
            ],
            user_content="Find Atlas",
            assistant_content="Atlas is found.",
        )

    formatted = transcript('{ "subject": "Atlas", "limit": 1 }')
    compact = transcript('{"limit":1,"subject":"Atlas"}')

    assert formatted == compact
    assert formatted[1]["tool_calls"] == (
        {"id": "call-1", "type": "function", "name": "lookup", "arguments": '{"limit":1,"subject":"Atlas"}'},
    )
    assert _canonical_messages_digest(formatted) == _canonical_messages_digest(compact)


@pytest.mark.parametrize("arguments", ["{", '{"key":1,"key":2}'])
def test_tool_arguments_reject_malformed_or_duplicate_key_json(arguments: str) -> None:
    with pytest.raises(ValueError, match="tool arguments"):
        _canonicalize_completed_messages(
            messages=[
                {"role": "user", "content": "Find Atlas"},
                {
                    "role": "assistant",
                    "content": "Calling lookup.",
                    "tool_calls": [{
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "lookup", "arguments": arguments},
                    }],
                },
                {"role": "tool", "content": "Atlas found", "tool_call_id": "call-1"},
                {"role": "assistant", "content": "Atlas is found."},
            ],
            user_content="Find Atlas",
            assistant_content="Atlas is found.",
        )


@pytest.mark.parametrize("messages", [
    [{"role": "user", "content": "x", "unknown": "x"}, {"role": "assistant", "content": "ok"}],
    [{"role": "user", "content": "x", "timestamp": "now", "unexpected": "x"}, {"role": "assistant", "content": "ok"}],
    [{"role": "user", "content": "x"}, {"role": "assistant", "content": "ok", "unexpected": "x"}],
    [{"role": "user", "content": "x"}, {"role": "tool", "content": "bad", "tool_call_id": "none", "unexpected": "x"}, {"role": "assistant", "content": "ok"}],
    [{"role": "user", "content": "x"}, {"role": "tool", "content": "bad", "tool_call_id": "none"}, {"role": "assistant", "content": "ok"}],
    [{"role": "user", "content": "x"}, {"role": "assistant", "content": "", "tool_calls": [{"id": "a", "type": "function", "function": {"name": "x", "arguments": "{"}}]}],
])
def test_full_transcript_canonicalization_rejects_invalid_messages(messages: list[dict[str, object]]) -> None:
    with pytest.raises(ValueError):
        _canonicalize_completed_messages(messages=messages, user_content="x", assistant_content="ok")
