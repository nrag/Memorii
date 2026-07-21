from __future__ import annotations

from memorii.core.llm_config import ResolvedLLMDecisionConfig
from memorii.core.memory_evolution import EnglishRuleMemoryExtractor
from memorii.core.memory_evolution.models import SourceObservation
from memorii.core.promotion.provider import PromotionAssessmentProviderError
from memorii.core.provider import factory as provider_factory
from memorii.core.provider.models import ProviderOperation
from memorii.core.work_state.service import WorkStateService


class _CountingExtractor(EnglishRuleMemoryExtractor):
    def __init__(self) -> None:
        self.calls = 0

    def extract(self, observations: list[SourceObservation]):
        self.calls += 1
        return super().extract(observations)


class _RaisingPromotionProvider:
    def decide(self, **_kwargs: object):
        raise PromotionAssessmentProviderError("configured promotion provider called")


def test_production_factory_wires_environment_selected_dependencies(monkeypatch) -> None:
    extractor = _CountingExtractor()
    promotion_provider = _RaisingPromotionProvider()
    received_configs: list[ResolvedLLMDecisionConfig] = []

    def build_extractor(*, config: ResolvedLLMDecisionConfig):
        received_configs.append(config)
        return extractor

    def build_promotion_provider(*, config: ResolvedLLMDecisionConfig):
        received_configs.append(config)
        return promotion_provider

    monkeypatch.setattr(provider_factory, "build_memory_extractor", build_extractor)
    monkeypatch.setattr(provider_factory, "build_promotion_decision_provider", build_promotion_provider)
    environment = {
        "MEMORII_DECISION_MODE": "hybrid",
        "MEMORII_LLM_PROVIDER": "none",
        "MEMORII_SECRET_SOURCE": "process",
    }
    work_states = WorkStateService()
    service = provider_factory.build_provider_memory_service_from_env(
        work_state_service=work_states,
        env=environment,
        reconcile_pending_evolution=False,
    )

    service.sync_event(
        operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
        content="Atlas migration owner is Alice.",
        operation_id="operation:factory-extractor",
    )
    state = work_states.open_or_resume_work(title="Factory wiring", task_id="task:factory")
    outcome = service.handle_tool_call(
        "memorii_record_outcome",
        {
            "work_state_id": state.work_state_id,
            "outcome": "completed",
            "content": "Factory composition completed",
        },
    )

    assert len(received_configs) == 2
    assert received_configs[0] is received_configs[1]
    assert received_configs[0].mode == "rule"
    assert extractor.calls == 1
    assert outcome.ok is True
    assert outcome.result["promotion_decision_error"] == "configured promotion provider called"


def test_production_factory_reconciles_by_default(monkeypatch) -> None:
    monkeypatch.setattr(
        provider_factory,
        "build_memory_extractor",
        lambda **_kwargs: EnglishRuleMemoryExtractor(),
    )
    monkeypatch.setattr(
        provider_factory,
        "build_promotion_decision_provider",
        lambda **_kwargs: _RaisingPromotionProvider(),
    )
    reconciliations: list[bool] = []
    original = provider_factory.ProviderMemoryService.reconcile_memory_evolution

    def record_reconciliation(self):
        reconciliations.append(True)
        return original(self)

    monkeypatch.setattr(
        provider_factory.ProviderMemoryService,
        "reconcile_memory_evolution",
        record_reconciliation,
    )

    provider_factory.build_provider_memory_service_from_env(env={})

    assert reconciliations == [True]
