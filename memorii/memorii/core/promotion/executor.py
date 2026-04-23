"""Applies promotion decisions to the canonical memory plane."""

from __future__ import annotations

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.promotion.models import PromotionAction, PromotionDecision, PromotionResult


class PromotionExecutor:
    def __init__(self, *, memory_plane: MemoryPlaneService) -> None:
        self._memory_plane = memory_plane

    def apply(self, *, candidate: CanonicalMemoryRecord, decision: PromotionDecision) -> PromotionResult:
        committed_memory_id: str | None = None

        if decision.action == PromotionAction.COMMIT:
            if decision.duplicate_of_memory_id is None:
                committed_memory_id = self._memory_plane.commit_candidate(
                    candidate_id=candidate.memory_id,
                    target_domain=decision.target_domain,
                    source_candidate_id=candidate.memory_id,
                    supersedes_memory_ids=decision.supersedes_memory_ids,
                )
            self._memory_plane.update_candidate_lifecycle(
                candidate_id=candidate.memory_id,
                promotion_state="promoted",
                duplicate_of_memory_id=decision.duplicate_of_memory_id,
                rejected_reason=None,
                conflict_with_memory_ids=decision.conflict_with_memory_ids,
                supersedes_memory_ids=decision.supersedes_memory_ids,
            )

        elif decision.action == PromotionAction.REJECT:
            self._memory_plane.update_candidate_lifecycle(
                candidate_id=candidate.memory_id,
                promotion_state="rejected",
                duplicate_of_memory_id=decision.duplicate_of_memory_id,
                rejected_reason=(
                    ";".join(code.value for code in decision.reason_codes)
                    if decision.reason_codes
                    else (";".join(decision.reasons) if decision.reasons else "rejected")
                ),
                conflict_with_memory_ids=decision.conflict_with_memory_ids,
                supersedes_memory_ids=decision.supersedes_memory_ids,
            )

        else:
            self._memory_plane.update_candidate_lifecycle(
                candidate_id=candidate.memory_id,
                promotion_state="staged",
                duplicate_of_memory_id=decision.duplicate_of_memory_id,
                rejected_reason=None,
                conflict_with_memory_ids=decision.conflict_with_memory_ids,
                supersedes_memory_ids=decision.supersedes_memory_ids,
            )

        return PromotionResult(
            candidate_id=candidate.memory_id,
            action=decision.action,
            target_domain=decision.target_domain,
            reason_codes=list(decision.reason_codes),
            reasons=list(decision.reasons),
            duplicate_of_memory_id=decision.duplicate_of_memory_id,
            supersedes_memory_ids=list(decision.supersedes_memory_ids),
            conflict_with_memory_ids=list(decision.conflict_with_memory_ids),
            decided_by=decision.decided_by,
            committed_memory_id=committed_memory_id,
        )
