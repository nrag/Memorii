"""First deterministic promotion policy implementation."""

from __future__ import annotations

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.promotion.models import PromotionAction, PromotionContext, PromotionDecision
from memorii.domain.enums import MemoryDomain


class RuleBasedPromotionDecider:
    """Conservative deterministic promotion policy."""

    def evaluate(self, *, candidate: CanonicalMemoryRecord, context: PromotionContext) -> PromotionDecision:
        if context.duplicates:
            return PromotionDecision(
                action=PromotionAction.KEEP_STAGED,
                target_domain=candidate.domain,
                reasons=["duplicate_committed_memory_exists"],
                duplicate_of_memory_id=context.duplicates[0].memory_id,
                decided_by="rule_based_v1",
                confidence=1.0,
            )

        if candidate.domain == MemoryDomain.EPISODIC:
            if context.possible_conflicts:
                return self._conflict_decision(candidate, context)
            if self._episodic_source_trusted(candidate):
                return self._commit(candidate, ["episodic_candidate_trusted_source"])
            return self._keep(candidate, ["episodic_source_not_trusted"])

        if candidate.domain == MemoryDomain.SEMANTIC:
            if not self._is_explicit_semantic_write(candidate):
                return self._reject(candidate, ["semantic_requires_explicit_memory_write"])
            if context.possible_conflicts:
                return self._conflict_decision(candidate, context)
            return self._commit(candidate, ["semantic_explicit_write_safe"])

        if candidate.domain == MemoryDomain.USER:
            if not self._is_explicit_user_write(candidate):
                return self._reject(candidate, ["user_memory_requires_explicit_memory_write_user"])
            if context.possible_conflicts:
                return self._conflict_decision(candidate, context)
            return self._commit(candidate, ["user_explicit_write_safe"])

        return self._keep(candidate, ["domain_not_auto_promoted_by_rule_based_v1"])

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
            reasons=["possible_conflict_with_committed_memory"],
            conflict_with_memory_ids=[item.memory_id for item in context.possible_conflicts],
            decided_by="rule_based_v1",
            confidence=0.6,
        )

    def _commit(self, candidate: CanonicalMemoryRecord, reasons: list[str]) -> PromotionDecision:
        return PromotionDecision(
            action=PromotionAction.COMMIT,
            target_domain=candidate.domain,
            reasons=reasons,
            decided_by="rule_based_v1",
            confidence=0.9,
        )

    def _reject(self, candidate: CanonicalMemoryRecord, reasons: list[str]) -> PromotionDecision:
        return PromotionDecision(
            action=PromotionAction.REJECT,
            target_domain=candidate.domain,
            reasons=reasons,
            decided_by="rule_based_v1",
            confidence=0.9,
        )

    def _keep(self, candidate: CanonicalMemoryRecord, reasons: list[str]) -> PromotionDecision:
        return PromotionDecision(
            action=PromotionAction.KEEP_STAGED,
            target_domain=candidate.domain,
            reasons=reasons,
            decided_by="rule_based_v1",
            confidence=0.75,
        )
