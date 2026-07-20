"""Independent structural checks for production provider retrieval composition."""

from __future__ import annotations

from memorii.core.memory_evolution import ProductionRetrievalDecision
from memorii.core.provider.models import (
    ProviderPrefetchResult,
    RetrievalChannelStatus,
)


def provider_composition_failure_buckets(
    result: ProviderPrefetchResult[ProductionRetrievalDecision],
) -> list[str]:
    """Detect composition drift without interpreting benchmark oracle semantics."""

    failures: list[str] = []
    decision = result.evolution_decision
    if decision is None:
        return ["runtime_production_decision_missing"]
    if result.evolution.selected_record_ids != decision.selected_record_ids:
        failures.append("runtime_evolution_channel_selection_mismatch")
    if result.evolution.status == RetrievalChannelStatus.ANSWER:
        if result.selected_channel != "evolution":
            failures.append("runtime_evolution_answer_not_selected")
        if not result.evolution.context or result.evolution.context not in result.context:
            failures.append("runtime_evolution_context_not_rendered")
    if result.selected_channel == "evolution" and not result.context:
        failures.append("runtime_selected_context_empty")
    return sorted(set(failures))
