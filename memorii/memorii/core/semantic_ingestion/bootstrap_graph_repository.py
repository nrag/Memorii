"""Thin current-authority ports over the dedicated bootstrap V3 store path."""

from __future__ import annotations

from typing import Protocol

from memorii.core.memory_evolution.ingestion_contracts import AuthenticatedIngressContext
from memorii.core.semantic_ingestion.contracts import (
    BootstrapCanonicalIdentityAuthorityWriteRequestV3,
    BootstrapCanonicalIdentityBindingAllocationReloadV3,
    BootstrapGraphControlEpochTransitionRequestV3,
    BootstrapGraphControlEpochTransitionResultV3,
    BootstrapGraphControlEpochV3,
    BootstrapGraphCurrentGenerationV3,
    BootstrapGraphDependentCoordinatorRequestV3,
    BootstrapGraphPlanAtomicReloadV3,
    BootstrapGraphPlanAtomicWriteRequestV3,
    BootstrapGraphTerminalPublicationRequestV3,
    BootstrapGraphTerminalReloadV3,
    BootstrapGraphTransactionAuthorityReloadV3,
    BootstrapGraphTransactionAuthorityWriteRequestV3,
    RequiredOutcomeScopeSet,
)


class _BootstrapGraphAtomicStoreV3(Protocol):
    def get_operation(self, operation_fence: object) -> object: ...

    def lease_binding(self, control: object) -> object: ...

    def publish_or_reload_bootstrap_graph_transaction_authority_v3(
        self, *, request: BootstrapGraphTransactionAuthorityWriteRequestV3,
    ) -> BootstrapGraphTransactionAuthorityReloadV3: ...

    def reload_bootstrap_graph_transaction_authority_for_recovery_v3(
        self,
        *,
        recovery_key_digest: str,
        authenticated_ingress: AuthenticatedIngressContext,
        required_outcome_scopes: RequiredOutcomeScopeSet,
        operation_fence_binding: object,
    ) -> BootstrapGraphTransactionAuthorityReloadV3 | None: ...

    def reload_bootstrap_semantic_reduction_authority_v3(
        self, *, normalization_replay: object,
    ) -> object | None: ...

    def transition_or_find_bootstrap_graph_control_epoch_v3(
        self, *, request: BootstrapGraphControlEpochTransitionRequestV3
    ) -> BootstrapGraphControlEpochTransitionResultV3: ...

    def load_bootstrap_graph_control_epoch_v3(
        self, *, request_core_digest: str
    ) -> BootstrapGraphControlEpochV3 | None: ...

    def checkpoint_bootstrap_graph_transaction_v3(
        self,
        *,
        request: BootstrapGraphPlanAtomicWriteRequestV3,
        authenticated_ingress: AuthenticatedIngressContext,
        required_outcome_scopes: RequiredOutcomeScopeSet,
        control_epoch: BootstrapGraphControlEpochV3,
    ) -> BootstrapGraphPlanAtomicReloadV3: ...

    def load_bootstrap_graph_current_generation_v3(
        self, *, request: BootstrapGraphDependentCoordinatorRequestV3,
        control_epoch: BootstrapGraphControlEpochV3,
        authenticated_ingress: AuthenticatedIngressContext,
        required_outcome_scopes: RequiredOutcomeScopeSet,
    ) -> BootstrapGraphCurrentGenerationV3: ...

    def reload_bootstrap_graph_transaction_v3(
        self,
        *,
        request: BootstrapGraphPlanAtomicWriteRequestV3,
        authenticated_ingress: AuthenticatedIngressContext,
        required_outcome_scopes: RequiredOutcomeScopeSet,
        control_epoch: BootstrapGraphControlEpochV3,
    ) -> BootstrapGraphPlanAtomicReloadV3: ...

    def reload_bootstrap_graph_retry_by_request_v3(
        self,
        *,
        request: BootstrapGraphDependentCoordinatorRequestV3,
        authenticated_ingress: AuthenticatedIngressContext,
        required_outcome_scopes: RequiredOutcomeScopeSet,
        control_epoch: BootstrapGraphControlEpochV3,
    ) -> BootstrapGraphPlanAtomicReloadV3 | None: ...

    def persist_bootstrap_graph_terminal_v3(
        self,
        *,
        request: BootstrapGraphTerminalPublicationRequestV3,
    ) -> BootstrapGraphTerminalReloadV3: ...

    def reload_bootstrap_graph_terminal_by_request_v3(
        self, *, request: BootstrapGraphDependentCoordinatorRequestV3,
    ) -> BootstrapGraphTerminalReloadV3 | None: ...

    def commit_or_reload_bootstrap_graph_group_v3(self, *, request: object) -> object: ...

    def publish_or_reload_bootstrap_canonical_identity_authority_v3(
        self, *, request: BootstrapCanonicalIdentityAuthorityWriteRequestV3,
    ) -> BootstrapCanonicalIdentityBindingAllocationReloadV3: ...


class AtomicStoreBootstrapGraphControlEpochRepositoryV3:
    """The append-only epoch repository; it exposes no mutable head API."""

    def __init__(self, *, atomic_store: _BootstrapGraphAtomicStoreV3) -> None:
        self._atomic_store = atomic_store

    def transition_or_find(
        self, *, request: BootstrapGraphControlEpochTransitionRequestV3
    ) -> BootstrapGraphControlEpochTransitionResultV3:
        validated = BootstrapGraphControlEpochTransitionRequestV3.model_validate(
            request.model_dump(mode="python")
        )
        return self._atomic_store.transition_or_find_bootstrap_graph_control_epoch_v3(
            request=validated
        )

    def load_current(self, *, request_core_digest: str) -> BootstrapGraphControlEpochV3 | None:
        return self._atomic_store.load_bootstrap_graph_control_epoch_v3(
            request_core_digest=request_core_digest
        )

    def refresh_current(
        self,
        *,
        request: BootstrapGraphDependentCoordinatorRequestV3,
        current_epoch: BootstrapGraphControlEpochV3,
    ) -> BootstrapGraphControlEpochTransitionResultV3:
        """Append or find the exact successor epoch for the store's current lease."""
        control = self._atomic_store.get_operation(
            current_epoch.operation_fence_binding
        )
        lease = self._atomic_store.lease_binding(control)
        if lease == current_epoch.operation_lease_binding:
            from memorii.core.semantic_ingestion.contracts import (
                BootstrapGraphControlEpochFoundV3,
            )

            return BootstrapGraphControlEpochFoundV3.create(
                kind="found", epoch=current_epoch
            )
        transition = (
            "lease_reclaimed"
            if lease.ownership_epoch > current_epoch.operation_lease_binding.ownership_epoch
            else "lease_renewed"
        )
        successor_request = BootstrapGraphControlEpochTransitionRequestV3.create(
            request_core_digest=request.request_core_digest,
            expected_epoch_digest=current_epoch.epoch_digest,
            transition=transition,
            normalization_replay=request.normalization_replay,
            graph_authority=request.graph_authority,
            authenticated_ingress=request.authenticated_ingress,
            required_outcome_scopes=request.required_outcome_scopes,
            operation_fence=current_epoch.operation_fence_binding,
            operation_lease=lease,
            writer_commit=current_epoch.writer_commit_binding,
        )
        return self.transition_or_find(request=successor_request)


class AtomicStoreBootstrapGraphTransactionAuthorityRepositoryV3:
    """Dedicated pre-epoch authority projection boundary.

    The repository deliberately exposes neither a mutable head nor a digest-only
    lookup: callers receive the exact store-reloaded projection and receipt.
    """

    def __init__(self, *, atomic_store: _BootstrapGraphAtomicStoreV3) -> None:
        self._atomic_store = atomic_store

    def publish_or_reload(
        self, *, request: BootstrapGraphTransactionAuthorityWriteRequestV3,
    ) -> BootstrapGraphTransactionAuthorityReloadV3:
        validated = BootstrapGraphTransactionAuthorityWriteRequestV3.model_validate(
            request.model_dump(mode="python")
        )
        return self._atomic_store.publish_or_reload_bootstrap_graph_transaction_authority_v3(
            request=validated
        )

    def reload_for_recovery(
        self,
        *,
        recovery_key_digest: str,
        authenticated_ingress: AuthenticatedIngressContext,
        required_outcome_scopes: RequiredOutcomeScopeSet,
        operation_fence_binding: object,
    ) -> BootstrapGraphTransactionAuthorityReloadV3 | None:
        return self._atomic_store.reload_bootstrap_graph_transaction_authority_for_recovery_v3(
            recovery_key_digest=recovery_key_digest,
            authenticated_ingress=authenticated_ingress,
            required_outcome_scopes=required_outcome_scopes,
            operation_fence_binding=operation_fence_binding,
        )


class AtomicStoreBootstrapSemanticReductionAuthorityRepositoryV3:
    """Exact retained reduction authority, never reconstructed from replay data."""

    def __init__(self, *, atomic_store: _BootstrapGraphAtomicStoreV3) -> None:
        self._atomic_store = atomic_store

    def reload(self, *, normalization_replay: object) -> object | None:
        return self._atomic_store.reload_bootstrap_semantic_reduction_authority_v3(
            normalization_replay=normalization_replay
        )


class AtomicStoreBootstrapCanonicalIdentityAuthorityRepositoryV3:
    """Dedicated pre-plan CAS/reload port for source-wide identity authority."""

    def __init__(self, *, atomic_store: _BootstrapGraphAtomicStoreV3) -> None:
        self._atomic_store = atomic_store

    def publish_or_reload(
        self, *, request: BootstrapCanonicalIdentityAuthorityWriteRequestV3,
    ) -> BootstrapCanonicalIdentityBindingAllocationReloadV3:
        validated = BootstrapCanonicalIdentityAuthorityWriteRequestV3.model_validate(
            request.model_dump(mode="python")
        )
        return self._atomic_store.publish_or_reload_bootstrap_canonical_identity_authority_v3(
            request=validated
        )


class AtomicStoreBootstrapGraphPlanRepositoryV3:
    """Publish/reload V3 plan, attempt, lineage, retry, and terminal closures."""

    def __init__(self, *, atomic_store: _BootstrapGraphAtomicStoreV3) -> None:
        self._atomic_store = atomic_store

    def publish_and_reload(
        self,
        *,
        request: BootstrapGraphPlanAtomicWriteRequestV3,
        authenticated_ingress: AuthenticatedIngressContext,
        required_outcome_scopes: RequiredOutcomeScopeSet,
        control_epoch: BootstrapGraphControlEpochV3,
    ) -> BootstrapGraphPlanAtomicReloadV3:
        validated = BootstrapGraphPlanAtomicWriteRequestV3.model_validate(
            request.model_dump(mode="python")
        )
        return self._atomic_store.checkpoint_bootstrap_graph_transaction_v3(
            request=validated,
            authenticated_ingress=authenticated_ingress,
            required_outcome_scopes=required_outcome_scopes,
            control_epoch=control_epoch,
        )

    def load_current_generation(
        self, *, request: BootstrapGraphDependentCoordinatorRequestV3,
        control_epoch: BootstrapGraphControlEpochV3,
        authenticated_ingress: AuthenticatedIngressContext,
        required_outcome_scopes: RequiredOutcomeScopeSet,
    ) -> BootstrapGraphCurrentGenerationV3:
        return self._atomic_store.load_bootstrap_graph_current_generation_v3(
            request=request, control_epoch=control_epoch,
            authenticated_ingress=authenticated_ingress,
            required_outcome_scopes=required_outcome_scopes,
        )

    def reload(
        self,
        *,
        request: BootstrapGraphPlanAtomicWriteRequestV3,
        authenticated_ingress: AuthenticatedIngressContext,
        required_outcome_scopes: RequiredOutcomeScopeSet,
        control_epoch: BootstrapGraphControlEpochV3,
    ) -> BootstrapGraphPlanAtomicReloadV3:
        validated = BootstrapGraphPlanAtomicWriteRequestV3.model_validate(
            request.model_dump(mode="python")
        )
        return self._atomic_store.reload_bootstrap_graph_transaction_v3(
            request=validated,
            authenticated_ingress=authenticated_ingress,
            required_outcome_scopes=required_outcome_scopes,
            control_epoch=control_epoch,
        )

    def reload_retry_by_request(
        self,
        *,
        request: BootstrapGraphDependentCoordinatorRequestV3,
        authenticated_ingress: AuthenticatedIngressContext,
        required_outcome_scopes: RequiredOutcomeScopeSet,
        control_epoch: BootstrapGraphControlEpochV3,
    ) -> BootstrapGraphPlanAtomicReloadV3 | None:
        return self._atomic_store.reload_bootstrap_graph_retry_by_request_v3(
            request=request,
            authenticated_ingress=authenticated_ingress,
            required_outcome_scopes=required_outcome_scopes,
            control_epoch=control_epoch,
        )


class AtomicStoreBootstrapGraphGroupCommitRepositoryV3:
    """The only V3 group-effect publication boundary.

    The atomic store owns both the CAS and the found-result reload.  Keeping
    this port separate from plan checkpoints prevents the coordinator from
    synthesizing an effect result after an acknowledgement loss.
    """

    def __init__(self, *, atomic_store: _BootstrapGraphAtomicStoreV3) -> None:
        self._atomic_store = atomic_store

    def commit_or_reload(self, *, request: object) -> object:
        from memorii.core.semantic_ingestion.contracts import (
            BootstrapGraphGroupCommitReloadV3,
            BootstrapGraphGroupCommitRequestV3,
        )

        if not isinstance(request, BootstrapGraphGroupCommitRequestV3):
            raise TypeError("bootstrap graph group commit request is not typed")
        validated = BootstrapGraphGroupCommitRequestV3.model_validate(
            request.model_dump(mode="python")
        )
        reload = self._atomic_store.commit_or_reload_bootstrap_graph_group_v3(
            request=validated
        )
        if not isinstance(reload, BootstrapGraphGroupCommitReloadV3):
            raise TypeError("bootstrap graph group commit reload is not typed")
        return BootstrapGraphGroupCommitReloadV3.model_validate(
            reload.model_dump(mode="python")
        )


class AtomicStoreBootstrapGraphTerminalPersistencePortV3:
    """The sole sealed V3 terminal publication boundary."""

    def __init__(self, *, atomic_store: _BootstrapGraphAtomicStoreV3) -> None:
        self._atomic_store = atomic_store

    def persist_and_reload(
        self,
        *,
        request: BootstrapGraphTerminalPublicationRequestV3,
    ) -> BootstrapGraphTerminalReloadV3:
        validated = BootstrapGraphTerminalPublicationRequestV3.model_validate(
            request.model_dump(mode="python")
        )
        return self._atomic_store.persist_bootstrap_graph_terminal_v3(
            request=validated,
        )

    def reload_by_request(
        self, *, request: BootstrapGraphDependentCoordinatorRequestV3,
    ) -> BootstrapGraphTerminalReloadV3 | None:
        validated = BootstrapGraphDependentCoordinatorRequestV3.model_validate(
            request.model_dump(mode="python")
        )
        return self._atomic_store.reload_bootstrap_graph_terminal_by_request_v3(
            request=validated,
        )


__all__ = [
    "AtomicStoreBootstrapGraphControlEpochRepositoryV3",
    "AtomicStoreBootstrapGraphTransactionAuthorityRepositoryV3",
    "AtomicStoreBootstrapSemanticReductionAuthorityRepositoryV3",
    "AtomicStoreBootstrapCanonicalIdentityAuthorityRepositoryV3",
    "AtomicStoreBootstrapGraphPlanRepositoryV3",
    "AtomicStoreBootstrapGraphGroupCommitRepositoryV3",
    "AtomicStoreBootstrapGraphTerminalPersistencePortV3",
]
