"""Promotion orchestration service with pluggable decision policy."""

from __future__ import annotations

from memorii.core.promotion.context_builder import PromotionContextBuilder
from memorii.core.promotion.executor import PromotionExecutor
from memorii.core.promotion.interfaces import PromotionDecider
from memorii.core.promotion.legacy_models import (
    BatchPromotionResult,
    PromotionAction,
    PromotionReasonCode,
    PromotionResult,
)
from memorii.domain.enums import MemoryDomain


class PromotionService:
    def __init__(
        self,
        *,
        context_builder: PromotionContextBuilder,
        decider: PromotionDecider,
        executor: PromotionExecutor,
    ) -> None:
        self._context_builder = context_builder
        self._decider = decider
        self._executor = executor

    def promote_candidate(self, candidate_id: str) -> PromotionResult:
        context = self._context_builder.build(candidate_id=candidate_id)
        decision = self._decider.evaluate(candidate=context.candidate, context=context)
        return self._executor.apply(candidate=context.candidate, decision=decision)

    def promote_candidates(
        self,
        *,
        task_id: str | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        domains: list[MemoryDomain] | None = None,
    ) -> BatchPromotionResult:
        candidates = [
            item
            for item in self._context_builder.list_staged_candidates()
            if (task_id is None or item.task_id == task_id)
            and (session_id is None or item.session_id == session_id)
            and (user_id is None or item.user_id == user_id)
            and (domains is None or item.domain in set(domains))
        ]
        results = [self.promote_candidate(item.memory_id) for item in candidates]
        return BatchPromotionResult(
            results=results,
            count_by_action=self._count_by_action(results),
            count_by_target_domain=self._count_by_target_domain(results),
            count_by_reason_code=self._count_by_reason_code(results),
            count_by_decider=self._count_by_decider(results),
        )

    def _count_by_action(self, results: list[PromotionResult]) -> dict[PromotionAction, int]:
        counts: dict[PromotionAction, int] = {}
        for result in results:
            counts[result.action] = counts.get(result.action, 0) + 1
        return counts

    def _count_by_target_domain(self, results: list[PromotionResult]) -> dict[MemoryDomain, int]:
        counts: dict[MemoryDomain, int] = {}
        for result in results:
            counts[result.target_domain] = counts.get(result.target_domain, 0) + 1
        return counts

    def _count_by_reason_code(self, results: list[PromotionResult]) -> dict[PromotionReasonCode, int]:
        counts: dict[PromotionReasonCode, int] = {}
        for result in results:
            for reason_code in result.reason_codes:
                counts[reason_code] = counts.get(reason_code, 0) + 1
        return counts

    def _count_by_decider(self, results: list[PromotionResult]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for result in results:
            counts[result.decided_by] = counts.get(result.decided_by, 0) + 1
        return counts
