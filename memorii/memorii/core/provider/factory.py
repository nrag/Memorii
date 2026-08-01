"""Application composition for provider memory services."""

from __future__ import annotations

from collections.abc import Mapping

from memorii.core.decision_state.service import DecisionStateService
from memorii.core.env_config import load_memorii_environment
from memorii.core.llm_config import ResolvedLLMDecisionConfig
from memorii.core.llm_decision.runtime_factory import build_promotion_decision_provider
from memorii.core.llm_decision.trace import LLMDecisionTraceStore
from memorii.core.memory_evolution.factory import build_memory_extractor
from memorii.core.memory_evolution.operation_store import EvolutionOperationRepository
from memorii.core.memory_evolution.query_analysis import QueryAnalyzer
from memorii.core.memory_evolution.query_analysis.runtime_factory import build_production_query_analyzer
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.work_state.service import WorkStateService

_DEFAULT_DECISION_STATE_SERVICE = object()


def build_provider_memory_service_from_env(
    *,
    memory_plane: MemoryPlaneService | None = None,
    work_state_service: WorkStateService | None = None,
    decision_state_service: DecisionStateService | None | object = _DEFAULT_DECISION_STATE_SERVICE,
    llm_decision_trace_store: LLMDecisionTraceStore | None = None,
    memory_evolution_query_analyzer: QueryAnalyzer | None = None,
    memory_evolution_operation_repository: EvolutionOperationRepository | None = None,
    env: Mapping[str, str] | None = None,
    reconcile_pending_evolution: bool = True,
) -> ProviderMemoryService:
    """Build the production provider composition from one environment snapshot."""

    snapshot = load_memorii_environment(env=env)
    config = ResolvedLLMDecisionConfig.from_env(snapshot.env)
    extractor = build_memory_extractor(config=config)
    promotion_provider = build_promotion_decision_provider(config=config)
    query_analyzer = memory_evolution_query_analyzer or build_production_query_analyzer(
        runtime_config=config.runtime,
    )
    if decision_state_service is _DEFAULT_DECISION_STATE_SERVICE:
        service = ProviderMemoryService(
            memory_plane=memory_plane,
            work_state_service=work_state_service,
            promotion_decision_provider=promotion_provider,
            llm_decision_trace_store=llm_decision_trace_store,
            memory_evolution_extractor=extractor,
            memory_evolution_query_analyzer=query_analyzer,
            memory_evolution_operation_repository=memory_evolution_operation_repository,
        )
    else:
        service = ProviderMemoryService(
            memory_plane=memory_plane,
            work_state_service=work_state_service,
            decision_state_service=decision_state_service,
            promotion_decision_provider=promotion_provider,
            llm_decision_trace_store=llm_decision_trace_store,
            memory_evolution_extractor=extractor,
            memory_evolution_query_analyzer=query_analyzer,
            memory_evolution_operation_repository=memory_evolution_operation_repository,
        )
    if reconcile_pending_evolution:
        service.reconcile_memory_evolution()
    return service


__all__ = ["build_provider_memory_service_from_env"]
