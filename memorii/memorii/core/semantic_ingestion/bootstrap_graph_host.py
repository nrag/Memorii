"""Host-owned composition boundary for the native bootstrap graph transaction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from memorii.core.memory_evolution.atomic_store import OperationLeaseBinding
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedIngressContext,
    OperationFenceBinding,
    SemanticWriterCommitBinding,
)
from memorii.core.semantic_ingestion.bootstrap_graph_coordinator import (
    BootstrapGraphDependentCoordinatorV3,
)
from memorii.core.semantic_ingestion.contracts import (
    BootstrapGraphControlEpochTransitionRequestV3,
    BootstrapGraphDependentCoordinatorRequestV3,
    BootstrapGraphDependentCoordinatorResultV3,
    BootstrapRecoveryReplayRecordV3,
    PreparedSource,
    RequiredOutcomeScopeSet,
)


@dataclass(frozen=True)
class BootstrapGraphAuthorityRequestV3:
    normalization_replay: BootstrapRecoveryReplayRecordV3
    prepared_source: PreparedSource
    authenticated_ingress: AuthenticatedIngressContext
    required_outcome_scopes: RequiredOutcomeScopeSet
    operation_fence_binding: OperationFenceBinding
    operation_lease_binding: OperationLeaseBinding
    writer_commit_binding: SemanticWriterCommitBinding


@dataclass(frozen=True)
class BootstrapGraphExecutionV3:
    coordinator: BootstrapGraphDependentCoordinatorV3
    request: BootstrapGraphDependentCoordinatorRequestV3
    transition: BootstrapGraphControlEpochTransitionRequestV3


class BootstrapGraphDependentAuthorityProviderV3(Protocol):
    def acquire(
        self, *, request: BootstrapGraphAuthorityRequestV3, atomic_store: object,
    ) -> BootstrapGraphExecutionV3 | None: ...


@dataclass(frozen=True)
class BootstrapGraphHostBundle:
    atomic_store: object
    promotion_enabled: bool = True

    def execute(
        self, *, request: BootstrapGraphAuthorityRequestV3,
    ) -> BootstrapGraphDependentCoordinatorResultV3 | None:
        if not self.promotion_enabled:
            return None
        from memorii.core.semantic_ingestion.bootstrap_graph_builtin import (
            build_builtin_bootstrap_graph_execution_v3,
        )

        execution = build_builtin_bootstrap_graph_execution_v3(
            request=request, atomic_store=self.atomic_store,
        )
        if execution is None:
            return None
        return execution.coordinator.coordinate(
            request=execution.request, transition=execution.transition,
        )

    def reload_terminal(
        self, *, normalization_replay: BootstrapRecoveryReplayRecordV3,
        authenticated_ingress: AuthenticatedIngressContext,
        required_outcome_scopes: RequiredOutcomeScopeSet,
        operation_fence_binding: OperationFenceBinding,
    ) -> object | None:
        reload_method = getattr(
            self.atomic_store, "reload_bootstrap_graph_terminal_by_recovery_v3", None
        )
        if reload_method is None:
            return None
        return reload_method(
            normalization_replay=normalization_replay,
            authenticated_ingress=authenticated_ingress,
            required_outcome_scopes=required_outcome_scopes,
            operation_fence_binding=operation_fence_binding,
        )


@dataclass(frozen=True)
class BootstrapGraphHostBundleBuilder:
    authority_provider: BootstrapGraphDependentAuthorityProviderV3
    promotion_enabled: bool = True

    def build(self, *, atomic_store: object) -> ScenarioBootstrapGraphHostBundle:
        return ScenarioBootstrapGraphHostBundle(
            atomic_store=atomic_store,
            authority_provider=self.authority_provider,
            promotion_enabled=self.promotion_enabled,
        )


@dataclass(frozen=True)
class ScenarioBootstrapGraphHostBundle(BootstrapGraphHostBundle):
    """Fixture-only authority injection retained below normal composition roots."""

    authority_provider: BootstrapGraphDependentAuthorityProviderV3 | None = None

    def execute(
        self, *, request: BootstrapGraphAuthorityRequestV3,
    ) -> BootstrapGraphDependentCoordinatorResultV3 | None:
        if not self.promotion_enabled or self.authority_provider is None:
            return None
        execution = self.authority_provider.acquire(
            request=request, atomic_store=self.atomic_store,
        )
        if execution is None:
            return None
        return execution.coordinator.coordinate(
            request=execution.request, transition=execution.transition,
        )


__all__ = [
    "BootstrapGraphAuthorityRequestV3",
    "BootstrapGraphDependentAuthorityProviderV3",
    "BootstrapGraphExecutionV3",
    "BootstrapGraphHostBundle",
    "BootstrapGraphHostBundleBuilder",
    "ScenarioBootstrapGraphHostBundle",
]
