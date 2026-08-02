"""Application composition for provider memory services."""

from __future__ import annotations

from memorii.core.decision_state.service import DecisionStateService
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.work_state.service import WorkStateService

_DEFAULT_DECISION_STATE_SERVICE = object()


def build_provider_memory_service_from_env(
    *,
    memory_plane: MemoryPlaneService | None = None,
    work_state_service: WorkStateService | None = None,
    decision_state_service: DecisionStateService | None | object = _DEFAULT_DECISION_STATE_SERVICE,
) -> ProviderMemoryService:
    """Build the source-only governed-source admission provider composition without ambient model dependencies."""

    return ProviderMemoryService(
        memory_plane=memory_plane,
        work_state_service=work_state_service,
        decision_state_service=None if decision_state_service is _DEFAULT_DECISION_STATE_SERVICE else decision_state_service,
    )


__all__ = ["build_provider_memory_service_from_env"]
