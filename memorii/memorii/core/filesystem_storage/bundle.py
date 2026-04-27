"""Filesystem-backed bootstrap helpers for Memorii JSONL stores."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from memorii.core.decision_state import DecisionStateService, JsonlDecisionStateStore
from memorii.core.filesystem_storage.maintenance import StorageRootStatus, ensure_within_soft_limits
from memorii.core.filesystem_storage.policy import FilesystemStoragePolicy
from memorii.core.llm_decision import (
    JsonlEvalSnapshotStore,
    JsonlGoldenCandidateStore,
    JsonlLLMDecisionTraceStore,
)
from memorii.core.memory_plane import JsonlMemoryPlaneStore, MemoryPlaneService
from memorii.core.provider.service import ProviderMemoryService
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
    ) -> "FilesystemStorageBundle":
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

    def build_provider_memory_service(self) -> ProviderMemoryService:
        return ProviderMemoryService(
            memory_plane=self.build_memory_plane_service(),
            work_state_service=self.build_work_state_service(),
            decision_state_service=self.build_decision_state_service(),
            llm_decision_trace_store=self.llm_trace_store,
        )

    def storage_status(self) -> StorageRootStatus:
        return ensure_within_soft_limits(root=self.storage_root, policy=self.policy)


def build_filesystem_provider(
    storage_root: str | Path,
    policy: FilesystemStoragePolicy | None = None,
) -> ProviderMemoryService:
    return FilesystemStorageBundle.from_root(storage_root=storage_root, policy=policy).build_provider_memory_service()
