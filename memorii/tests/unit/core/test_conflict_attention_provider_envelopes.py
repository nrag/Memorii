from __future__ import annotations

from datetime import UTC, datetime

import pytest
from memorii.core.memory_evolution.conflict_attention import (
    ConflictAttention,
    ConflictAttentionObservabilityEvent,
    ConflictAttentionPage,
    ConflictAudience,
    ConflictKind,
    ConflictResolutionOption,
    ConflictStatus,
)
from memorii.core.provider.attention_models import (
    ProviderPrefetchAttentionEnvelope,
    ProviderToolAttentionEnvelope,
)
from memorii.core.provider.models import (
    ProviderPrefetchResult,
    RetrievalChannelAuthority,
    RetrievalChannelResult,
    RetrievalChannelStatus,
)
from memorii.core.provider.tools import ProviderToolCallResult
from pydantic import ValidationError


def _prefetch_result() -> ProviderPrefetchResult:
    channel = RetrievalChannelResult(
        channel="canonical",
        status=RetrievalChannelStatus.NO_MATCH,
        authority=RetrievalChannelAuthority.NONE,
        context="",
    )
    evolution = channel.model_copy(update={"channel": "evolution"})
    return ProviderPrefetchResult(
        context="",
        selected_channel="none",
        canonical=channel,
        evolution=evolution,
        evolution_decision=None,
    )


def _item(index: int) -> ConflictAttention:
    return ConflictAttention(
        conflict_id=f"conflict-{index}",
        conflict_revision="a" * 64,
        kind=ConflictKind.SEMANTIC_DISAGREEMENT,
        audience=ConflictAudience.USER,
        status=ConflictStatus.OPEN,
        question="Which statement is correct?",
        options=(
            ConflictResolutionOption(candidate_id=f"candidate-{index}-a", label="A", statement="A", candidate_digest="b" * 64),
            ConflictResolutionOption(candidate_id=f"candidate-{index}-b", label="B", statement="B", candidate_digest="c" * 64),
        ),
        created_at=datetime(2026, 8, 2, tzinfo=UTC),
        creation_coordinate=index,
        scope_digest="d" * 64,
    )
def test_attention_envelope_wraps_without_changing_legacy_serialization() -> None:
    legacy = _prefetch_result()
    envelope = ProviderPrefetchAttentionEnvelope(
        legacy_result=legacy,
        attention_required=ConflictAttentionPage(total_pending=0),
    )
    assert envelope.model_dump(mode="json")["protocol"] == "memorii.conflict-attention.v1"
    assert envelope.legacy_result.model_dump(mode="json") == legacy.model_dump(mode="json")
    schema = ProviderPrefetchAttentionEnvelope.model_json_schema()
    assert schema["properties"]["attention_required"]["$ref"].endswith("/ConflictAttentionPage")
    with pytest.raises(ValidationError):
        ProviderPrefetchAttentionEnvelope.model_validate(
            {"legacy_result": legacy, "attention_required": ConflictAttentionPage(total_pending=0), "unexpected": True}
        )


def test_prefetch_envelope_requires_a_legacy_instance_and_snapshots_wire_bytes() -> None:
    legacy = _prefetch_result()
    page = ConflictAttentionPage(total_pending=0)
    envelope = ProviderPrefetchAttentionEnvelope(legacy_result=legacy, attention_required=page)
    expected = envelope.model_dump_json()
    legacy.canonical.context = "mutated-original"
    envelope.legacy_result.canonical.context = "mutated-envelope"
    assert envelope.model_dump_json() == expected
    assert envelope.model_copy().model_dump_json() == expected
    with pytest.raises(ValueError, match="cannot update"):
        envelope.model_copy(update={"protocol": "memorii.conflict-attention.v1"})
    with pytest.raises(ValidationError, match="validated ProviderPrefetchResult"):
        ProviderPrefetchAttentionEnvelope.model_validate(
            {"legacy_result": legacy.model_dump(), "attention_required": page}
        )


def test_tool_attention_envelope_is_separate_from_legacy_tool_result() -> None:
    legacy = ProviderToolCallResult(tool_name="get_state_summary", ok=True)
    envelope = ProviderToolAttentionEnvelope(legacy_result=legacy, attention_required=ConflictAttentionPage(total_pending=0))
    assert envelope.legacy_result.model_dump(mode="json") == legacy.model_dump(mode="json")
    with pytest.raises(ValidationError):
        ProviderToolAttentionEnvelope.model_validate(
            {"legacy_result": legacy, "attention_required": ConflictAttentionPage(total_pending=0), "unexpected": True}
        )
    expected = envelope.model_dump_json()
    legacy.result["changed"] = True
    envelope.legacy_result.result["changed"] = True
    assert envelope.model_dump_json() == expected
    assert envelope.model_copy(deep=True).model_dump_json() == expected
    with pytest.raises(ValueError, match="cannot update"):
        envelope.model_copy(update={"protocol": "memorii.conflict-attention.v1"})
    with pytest.raises(ValidationError, match="validated ProviderToolCallResult"):
        ProviderToolAttentionEnvelope.model_validate(
            {"legacy_result": legacy.model_dump(), "attention_required": ConflictAttentionPage(total_pending=0)}
        )


def test_standalone_attention_page_allows_the_hundred_item_list_cap() -> None:
    page = ConflictAttentionPage(items=tuple(_item(index) for index in range(100)), total_pending=100)
    assert len(page.items) == 100


def test_provider_envelopes_cap_embedded_attention_at_three() -> None:
    page = ConflictAttentionPage(items=tuple(_item(index) for index in range(4)), total_pending=4)
    with pytest.raises(ValidationError, match="embedded page size"):
        ProviderPrefetchAttentionEnvelope(legacy_result=_prefetch_result(), attention_required=page)
    with pytest.raises(ValidationError, match="embedded page size"):
        ProviderToolAttentionEnvelope(legacy_result=ProviderToolCallResult(tool_name="x", ok=True), attention_required=page)


def test_observability_event_rejects_unknown_or_untyped_dimensions() -> None:
    event = ConflictAttentionObservabilityEvent(
        conflict_id="conflict-1",
        kind=ConflictKind.SEMANTIC_DISAGREEMENT,
        status=ConflictStatus.OPEN,
        scope_digest="d" * 64,
    )
    payload = event.model_dump()

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ConflictAttentionObservabilityEvent.model_validate(
            {**payload, "question": "sensitive text"}
        )
    with pytest.raises(ValidationError, match="instance of ConflictKind"):
        ConflictAttentionObservabilityEvent.model_validate(
            {**payload, "kind": "semantic_disagreement"}
        )
