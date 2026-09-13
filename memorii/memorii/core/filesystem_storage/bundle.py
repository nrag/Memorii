"""Filesystem-backed bootstrap helpers for Memorii JSONL stores."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from memorii.core.decision_state import DecisionStateService, JsonlDecisionStateStore
from memorii.core.filesystem_storage.maintenance import StorageRootStatus, ensure_within_soft_limits
from memorii.core.filesystem_storage.policy import FilesystemStoragePolicy
from memorii.core.llm_decision import (
    JsonlEvalSnapshotStore,
    JsonlGoldenCandidateStore,
    JsonlLLMDecisionTraceStore,
)
from memorii.core.memory_evolution.bootstrap_profile import (
    HostBootstrapCapability,
    HostBootstrapMaterialVerifier,
)
from memorii.core.memory_evolution.conflict_attention import (
    ConflictAttentionObservabilitySink,
)
from memorii.core.memory_evolution.conflict_attention_repository import (
    ConflictClarificationRepository,
    ConflictCursorKey,
    FileConflictAttentionRepository,
)
from memorii.core.memory_evolution.conflict_integrity import (
    PrivilegedSemanticIntegrityLifecycle,
)
from memorii.core.memory_plane import JsonlMemoryPlaneStore, MemoryPlaneService
from memorii.core.provider.factory import build_provider_memory_service_from_env
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.scoped_context.authority import ScopedHostReadAuthority
from memorii.core.semantic_ingestion.production_authority import (
    VerifiedProductionHostAuthority,
)
from memorii.core.semantic_ingestion.source_normalization_host import SourceNormalizationHostBundleBuilder
from memorii.core.work_state import JsonlWorkStateStore, WorkStateService


@dataclass(frozen=True)
class FilesystemStorageBundle:
    storage_root: Path
    policy: FilesystemStoragePolicy
    work_state_store: JsonlWorkStateStore
    decision_state_store: JsonlDecisionStateStore
    memory_plane_store: JsonlMemoryPlaneStore
    llm_trace_store: JsonlLLMDecisionTraceStore
    eval_snapshot_store: JsonlEvalSnapshotStore
    golden_candidate_store: JsonlGoldenCandidateStore

    @classmethod
    def from_root(
        cls,
        storage_root: str | Path,
        policy: FilesystemStoragePolicy | None = None,
    ) -> FilesystemStorageBundle:
        resolved_root = Path(storage_root)
        resolved_root.mkdir(parents=True, exist_ok=True)
        resolved_policy = policy or FilesystemStoragePolicy()

        bundle = cls(
            storage_root=resolved_root,
            policy=resolved_policy,
            work_state_store=JsonlWorkStateStore(resolved_root / "work_state"),
            decision_state_store=JsonlDecisionStateStore(resolved_root / "decision_state"),
            memory_plane_store=JsonlMemoryPlaneStore(resolved_root / "memory_plane"),
            llm_trace_store=JsonlLLMDecisionTraceStore(resolved_root / "llm_decision" / "traces.jsonl"),
            eval_snapshot_store=JsonlEvalSnapshotStore(resolved_root / "llm_decision" / "eval_snapshots.jsonl"),
            golden_candidate_store=JsonlGoldenCandidateStore(
                resolved_root / "llm_decision" / "golden_candidates.jsonl"
            ),
        )
        ensure_within_soft_limits(root=bundle.storage_root, policy=bundle.policy)
        return bundle

    def build_memory_plane_service(self) -> MemoryPlaneService:
        return MemoryPlaneService(record_store=self.memory_plane_store)

    def build_work_state_service(self) -> WorkStateService:
        return WorkStateService(store=self.work_state_store)

    def build_decision_state_service(self) -> DecisionStateService:
        return DecisionStateService(store=self.decision_state_store)

    def build_provider_memory_service(
        self,
        *,
        memory_plane: MemoryPlaneService | None = None,
        semantic_integrity_lifecycle: PrivilegedSemanticIntegrityLifecycle
        | None = None,
        host_bootstrap_capability: HostBootstrapCapability | None = None,
        host_bootstrap_material_verifier: HostBootstrapMaterialVerifier | None = None,
        source_normalization_host_bundle_builder: SourceNormalizationHostBundleBuilder | None = None,
        verified_production_host_authority: VerifiedProductionHostAuthority | None = None,
        conflict_attention_repository: ConflictClarificationRepository | None = None,
        conflict_attention_enabled: bool = False,
        conflict_attention_observability_sink: ConflictAttentionObservabilitySink
        | None = None,
        conflict_attention_composite: bool = False,
        now_provider: Callable[[], datetime] | None = None,
        scoped_read_authority: ScopedHostReadAuthority | None = None,
    ) -> ProviderMemoryService:
        return build_provider_memory_service_from_env(
            memory_plane=memory_plane or self.build_memory_plane_service(),
            work_state_service=self.build_work_state_service(),
            decision_state_service=self.build_decision_state_service(),
            semantic_integrity_lifecycle=semantic_integrity_lifecycle,
            semantic_integrity_root=(
                None
                if semantic_integrity_lifecycle is not None
                else self.storage_root / "semantic_integrity"
            ),
            host_bootstrap_capability=host_bootstrap_capability,
            host_bootstrap_material_verifier=host_bootstrap_material_verifier,
            source_normalization_host_bundle_builder=source_normalization_host_bundle_builder,
            verified_production_host_authority=verified_production_host_authority,
            conflict_attention_repository=conflict_attention_repository,
            conflict_attention_enabled=conflict_attention_enabled,
            conflict_attention_observability_sink=conflict_attention_observability_sink,
            conflict_attention_composite=conflict_attention_composite,
            now_provider=now_provider,
            scoped_read_authority=scoped_read_authority,
        )

    def build_conflict_attention_repository(
        self, keys: tuple[ConflictCursorKey, ...]
    ) -> FileConflictAttentionRepository:
        """Build the file-backed conflict-attention ledger for this root."""
        return FileConflictAttentionRepository(
            self.storage_root / "conflict_attention", keys=keys
        )

    def storage_status(self) -> StorageRootStatus:
        return ensure_within_soft_limits(root=self.storage_root, policy=self.policy)


def build_filesystem_provider(
    storage_root: str | Path,
    policy: FilesystemStoragePolicy | None = None,
    *,
    memory_plane: MemoryPlaneService | None = None,
    semantic_integrity_lifecycle: PrivilegedSemanticIntegrityLifecycle
    | None = None,
    host_bootstrap_capability: HostBootstrapCapability | None = None,
    host_bootstrap_material_verifier: HostBootstrapMaterialVerifier | None = None,
    source_normalization_host_bundle_builder: SourceNormalizationHostBundleBuilder | None = None,
    verified_production_host_authority: VerifiedProductionHostAuthority | None = None,
    conflict_attention_repository: ConflictClarificationRepository | None = None,
    conflict_attention_enabled: bool = False,
    conflict_attention_observability_sink: ConflictAttentionObservabilitySink
    | None = None,
    conflict_attention_composite: bool = False,
    now_provider: Callable[[], datetime] | None = None,
    scoped_read_authority: ScopedHostReadAuthority | None = None,
) -> ProviderMemoryService:
    return FilesystemStorageBundle.from_root(
        storage_root=storage_root, policy=policy
    ).build_provider_memory_service(
        memory_plane=memory_plane,
        semantic_integrity_lifecycle=semantic_integrity_lifecycle,
        host_bootstrap_capability=host_bootstrap_capability,
        host_bootstrap_material_verifier=host_bootstrap_material_verifier,
        source_normalization_host_bundle_builder=source_normalization_host_bundle_builder,
        verified_production_host_authority=verified_production_host_authority,
        conflict_attention_repository=conflict_attention_repository,
        conflict_attention_enabled=conflict_attention_enabled,
        conflict_attention_observability_sink=conflict_attention_observability_sink,
        conflict_attention_composite=conflict_attention_composite,
        now_provider=now_provider,
        scoped_read_authority=scoped_read_authority,
    )
