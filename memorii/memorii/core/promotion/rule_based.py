"""First deterministic promotion policy implementation."""

from __future__ import annotations

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.promotion.models import (
    PromotionAction,
    PromotionContext,
    PromotionDecision,
    PromotionReasonCode,
)
from memorii.domain.enums import MemoryDomain


class RuleBasedPromotionDecider:
    """Conservative deterministic promotion policy."""

    def evaluate(self, *, candidate: CanonicalMemoryRecord, context: PromotionContext) -> PromotionDecision:
        if context.duplicates:
            return PromotionDecision(
                action=PromotionAction.KEEP_STAGED,
                target_domain=candidate.domain,
                reason_codes=[PromotionReasonCode.DUPLICATE_COMMITTED_MEMORY_EXISTS],
                duplicate_of_memory_id=context.duplicates[0].memory_id,
                decided_by="rule_based_v1",
                confidence=1.0,
            )

        if candidate.domain == MemoryDomain.EPISODIC:
            if context.possible_conflicts:
                return self._conflict_decision(candidate, context)
            if self._episodic_source_trusted(candidate):
                return self._commit(candidate, [PromotionReasonCode.EPISODIC_CANDIDATE_TRUSTED_SOURCE])
            return self._keep(candidate, [PromotionReasonCode.EPISODIC_SOURCE_NOT_TRUSTED])

        if candidate.domain == MemoryDomain.SEMANTIC:
            if not self._is_explicit_semantic_write(candidate):
                return self._reject(candidate, [PromotionReasonCode.SEMANTIC_REQUIRES_EXPLICIT_MEMORY_WRITE])
            if context.possible_conflicts:
                return self._conflict_decision(candidate, context)
            return self._commit(candidate, [PromotionReasonCode.SEMANTIC_EXPLICIT_WRITE_SAFE])

        if candidate.domain == MemoryDomain.USER:
            if not self._is_explicit_user_write(candidate):
                return self._reject(
                    candidate,
                    [PromotionReasonCode.USER_MEMORY_REQUIRES_EXPLICIT_MEMORY_WRITE_USER],
                )
            if context.possible_conflicts:
                return self._conflict_decision(candidate, context)
            return self._commit(candidate, [PromotionReasonCode.USER_EXPLICIT_WRITE_SAFE])

        return self._keep(candidate, [PromotionReasonCode.DOMAIN_NOT_AUTO_PROMOTED])

    def _episodic_source_trusted(self, candidate: CanonicalMemoryRecord) -> bool:
        trusted_markers = ("provider", "runtime", "session_summary", "structured")
        return any(marker in candidate.source_kind for marker in trusted_markers)

    def _is_explicit_semantic_write(self, candidate: CanonicalMemoryRecord) -> bool:
        return "memory_write_longterm" in candidate.source_kind

    def _is_explicit_user_write(self, candidate: CanonicalMemoryRecord) -> bool:
        return "memory_write_user" in candidate.source_kind

    def _conflict_decision(self, candidate: CanonicalMemoryRecord, context: PromotionContext) -> PromotionDecision:
        return PromotionDecision(
            action=PromotionAction.KEEP_STAGED,
            target_domain=candidate.domain,
            reason_codes=[PromotionReasonCode.POSSIBLE_CONFLICT_WITH_COMMITTED_MEMORY],
            conflict_with_memory_ids=[item.memory_id for item in context.possible_conflicts],
            decided_by="rule_based_v1",
            confidence=0.6,
        )

    def _commit(self, candidate: CanonicalMemoryRecord, reason_codes: list[PromotionReasonCode]) -> PromotionDecision:
        return PromotionDecision(
            action=PromotionAction.COMMIT,
            target_domain=candidate.domain,
            reason_codes=reason_codes,
            decided_by="rule_based_v1",
            confidence=0.9,
        )

    def _reject(self, candidate: CanonicalMemoryRecord, reason_codes: list[PromotionReasonCode]) -> PromotionDecision:
        return PromotionDecision(
            action=PromotionAction.REJECT,
            target_domain=candidate.domain,
            reason_codes=reason_codes,
            decided_by="rule_based_v1",
            confidence=0.9,
        )

    def _keep(self, candidate: CanonicalMemoryRecord, reason_codes: list[PromotionReasonCode]) -> PromotionDecision:
        return PromotionDecision(
            action=PromotionAction.KEEP_STAGED,
            target_domain=candidate.domain,
            reason_codes=reason_codes,
            decided_by="rule_based_v1",
            confidence=0.75,
        )
