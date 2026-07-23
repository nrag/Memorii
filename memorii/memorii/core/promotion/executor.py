"""Applies promotion decisions to the canonical memory plane."""

from __future__ import annotations

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.promotion.execution_contracts import PromotionAction, PromotionExecutionPlan, PromotionExecutionResult


class PromotionExecutor:
    def __init__(self, *, memory_plane: MemoryPlaneService) -> None:
        self._memory_plane = memory_plane

    def apply(self, *, candidate: CanonicalMemoryRecord, plan: PromotionExecutionPlan) -> PromotionExecutionResult:
        committed_memory_id: str | None = None

        if plan.action == PromotionAction.COMMIT:
            if plan.duplicate_of_memory_id is None:
                committed_memory_id = self._memory_plane.commit_candidate(
                    candidate_id=candidate.memory_id,
                    target_domain=plan.target_domain,
                    source_candidate_id=candidate.memory_id,
                    supersedes_memory_ids=plan.supersedes_memory_ids,
                )
            self._memory_plane.update_candidate_lifecycle(
                candidate_id=candidate.memory_id,
                promotion_state="promoted",
                duplicate_of_memory_id=plan.duplicate_of_memory_id,
                rejected_reason=None,
                conflict_with_memory_ids=plan.conflict_with_memory_ids,
                supersedes_memory_ids=plan.supersedes_memory_ids,
            )

        elif plan.action == PromotionAction.REJECT:
            self._memory_plane.update_candidate_lifecycle(
                candidate_id=candidate.memory_id,
                promotion_state="rejected",
                duplicate_of_memory_id=plan.duplicate_of_memory_id,
                rejected_reason=(
                    ";".join(code.value for code in plan.reason_codes)
                    if plan.reason_codes
                    else (";".join(plan.reasons) if plan.reasons else "rejected")
                ),
                conflict_with_memory_ids=plan.conflict_with_memory_ids,
                supersedes_memory_ids=plan.supersedes_memory_ids,
            )

        else:
            self._memory_plane.update_candidate_lifecycle(
                candidate_id=candidate.memory_id,
                promotion_state="staged",
                duplicate_of_memory_id=plan.duplicate_of_memory_id,
                rejected_reason=None,
                conflict_with_memory_ids=plan.conflict_with_memory_ids,
                supersedes_memory_ids=plan.supersedes_memory_ids,
            )

        return PromotionExecutionResult(
            candidate_id=candidate.memory_id,
            action=plan.action,
            target_domain=plan.target_domain,
            reason_codes=list(plan.reason_codes),
            reasons=list(plan.reasons),
            duplicate_of_memory_id=plan.duplicate_of_memory_id,
            supersedes_memory_ids=list(plan.supersedes_memory_ids),
            conflict_with_memory_ids=list(plan.conflict_with_memory_ids),
            decided_by=plan.decided_by,
            committed_memory_id=committed_memory_id,
        )
