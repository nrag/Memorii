from __future__ import annotations

import pytest
from memorii.core.semantic_ingestion.hermes_completed_turn_runtime import _canonicalize_completed_messages


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


@pytest.mark.parametrize("messages", [
    [{"role": "user", "content": "x", "unknown": "x"}, {"role": "assistant", "content": "ok"}],
    [{"role": "user", "content": "x"}, {"role": "tool", "content": "bad", "tool_call_id": "none"}, {"role": "assistant", "content": "ok"}],
    [{"role": "user", "content": "x"}, {"role": "assistant", "content": "", "tool_calls": [{"id": "a", "type": "function", "function": {"name": "x", "arguments": "{ }"}}]}],
])
def test_full_transcript_canonicalization_rejects_invalid_messages(messages: list[dict[str, object]]) -> None:
    with pytest.raises(ValueError):
        _canonicalize_completed_messages(messages=messages, user_content="x", assistant_content="ok")
