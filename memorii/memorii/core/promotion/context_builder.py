"""Deterministic promotion context normalization."""

from __future__ import annotations

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.promotion.models import PromotionContext
from memorii.domain.enums import CommitStatus


class PromotionContextBuilder:
    def __init__(self, *, memory_plane: MemoryPlaneService) -> None:
        self._memory_plane = memory_plane

    def build(self, *, candidate_id: str) -> PromotionContext:
        candidate = self._memory_plane.get_record(candidate_id)
        if candidate is None:
            raise ValueError(f"candidate not found: {candidate_id}")
        if candidate.status != CommitStatus.CANDIDATE:
            raise ValueError(f"record is not a staged candidate: {candidate_id}")

        in_scope = [item for item in self._memory_plane.list_records() if self._same_scope(item, candidate)]
        committed_in_scope = [item for item in in_scope if item.status == CommitStatus.COMMITTED]
        candidates_in_scope = [item for item in in_scope if item.status == CommitStatus.CANDIDATE and item.memory_id != candidate.memory_id]

        same_domain_committed = [item for item in committed_in_scope if item.domain == candidate.domain]
        same_domain_candidates = [item for item in candidates_in_scope if item.domain == candidate.domain]

        duplicates = [item for item in same_domain_committed if self._is_duplicate(item, candidate)]
        conflicts = [item for item in same_domain_committed if self._is_conflict(item, candidate)]

        return PromotionContext(
            candidate=candidate,
            committed_in_scope=committed_in_scope,
            candidates_in_scope=candidates_in_scope,
            same_domain_committed=same_domain_committed,
            same_domain_candidates=same_domain_candidates,
            duplicates=duplicates,
            possible_conflicts=conflicts,
        )

    def list_staged_candidates(self) -> list[CanonicalMemoryRecord]:
        return self._memory_plane.list_records(status=CommitStatus.CANDIDATE)

    def _same_scope(self, lhs: CanonicalMemoryRecord, rhs: CanonicalMemoryRecord) -> bool:
        return (
            lhs.task_id == rhs.task_id
            and lhs.session_id == rhs.session_id
            and lhs.user_id == rhs.user_id
            and lhs.execution_node_id == rhs.execution_node_id
            and lhs.solver_run_id == rhs.solver_run_id
        )

    def _is_duplicate(self, existing: CanonicalMemoryRecord, candidate: CanonicalMemoryRecord) -> bool:
        return existing.text.strip().lower() == candidate.text.strip().lower()

    def _is_conflict(self, existing: CanonicalMemoryRecord, candidate: CanonicalMemoryRecord) -> bool:
        if self._is_duplicate(existing, candidate):
            return False
        if existing.domain != candidate.domain:
            return False
        if existing.valid_to is not None and candidate.valid_from is not None and existing.valid_to < candidate.valid_from:
            return False
        if candidate.valid_to is not None and existing.valid_from is not None and candidate.valid_to < existing.valid_from:
            return False
        return True
