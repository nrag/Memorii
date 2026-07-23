from typing import Literal

from memorii.core.benchmark.memory_evolution_runtime.provider_composition import (
    provider_composition_failure_buckets,
)
from memorii.core.memory_evolution import (
    ProductionRetrievalDecision,
    QueryTemporalFrame,
    QueryTemporalKind,
    SemanticFrameStatus,
)
from memorii.core.provider.models import (
    ProviderPrefetchResult,
    RetrievalChannelAuthority,
    RetrievalChannelResult,
    RetrievalChannelStatus,
)


def _decision() -> ProductionRetrievalDecision:
    return ProductionRetrievalDecision(
        query="Who owns Atlas?",
        semantic_frame_status=SemanticFrameStatus.MATCHED,
        temporal_frame=QueryTemporalFrame(
            temporal_kind=QueryTemporalKind.CURRENT,
            resolution_confidence=1.0,
        ),
        selected_record_ids=["claim:owner"],
        supporting_record_ids=["claim:owner"],
    )


def _channel(
    *,
    channel: Literal["canonical", "evolution"],
    status: RetrievalChannelStatus,
    authority: RetrievalChannelAuthority,
    context: str,
    selected_record_ids: list[str],
) -> RetrievalChannelResult:
    return RetrievalChannelResult(
        channel=channel,
        status=status,
        authority=authority,
        context=context,
        selected_record_ids=selected_record_ids,
    )


def test_composition_audit_accepts_rendered_authoritative_evolution_answer() -> None:
    context = "Evolution memory (production retrieval):\n- Atlas owner = Bob"
    result = ProviderPrefetchResult[ProductionRetrievalDecision](
        context=context,
        selected_channel="evolution",
        canonical=_channel(
            channel="canonical",
            status=RetrievalChannelStatus.NO_MATCH,
            authority=RetrievalChannelAuthority.NONE,
            context="",
            selected_record_ids=[],
        ),
        evolution=_channel(
            channel="evolution",
            status=RetrievalChannelStatus.ANSWER,
            authority=RetrievalChannelAuthority.AUTHORITATIVE,
            context=context,
            selected_record_ids=["claim:owner"],
        ),
        evolution_decision=_decision(),
    )

    assert provider_composition_failure_buckets(result) == []


def test_composition_audit_rejects_false_success_when_decision_is_not_rendered() -> None:
    result = ProviderPrefetchResult[ProductionRetrievalDecision](
        context="stale canonical answer",
        selected_channel="canonical",
        canonical=_channel(
            channel="canonical",
            status=RetrievalChannelStatus.ANSWER,
            authority=RetrievalChannelAuthority.AUTHORITATIVE,
            context="stale canonical answer",
            selected_record_ids=["canonical:stale"],
        ),
        evolution=_channel(
            channel="evolution",
            status=RetrievalChannelStatus.ANSWER,
            authority=RetrievalChannelAuthority.AUTHORITATIVE,
            context="current evolution answer",
            selected_record_ids=["claim:different"],
        ),
        evolution_decision=_decision(),
    )

    assert provider_composition_failure_buckets(result) == [
        "runtime_evolution_answer_not_selected",
        "runtime_evolution_channel_selection_mismatch",
        "runtime_evolution_context_not_rendered",
    ]
