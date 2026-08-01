from __future__ import annotations

from memorii.core.provider import factory as provider_factory
from memorii.core.work_state.service import WorkStateService


def test_production_factory_constructs_only_source_admission_dependencies() -> None:
    work_states = WorkStateService()
    service = provider_factory.build_provider_memory_service_from_env(
        work_state_service=work_states,
    )
    assert service._memory_evolution_service is None
    assert not hasattr(service, "_evolution_coordinator")


def test_production_factory_exposes_no_reconciliation_path() -> None:
    service = provider_factory.build_provider_memory_service_from_env()
    assert service.reconcile_memory_evolution() == []
