"""Deterministic belief update provider wrapping solver belief heuristics."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from memorii.core.belief.models import BeliefUpdateContext, BeliefUpdateDecision
from memorii.core.llm_decision.models import (
    LLMDecisionMode,
    LLMDecisionPoint,
    LLMDecisionStatus,
    LLMDecisionTrace,
)
from memorii.core.solver.belief import update_solver_belief


class RuleBasedBeliefUpdateProvider:
    def update(self, *, context: BeliefUpdateContext) -> tuple[BeliefUpdateDecision, LLMDecisionTrace]:
        belief = update_solver_belief(
            prior_belief=context.prior_belief,
            decision=context.decision,
            evidence_count=context.evidence_count,
            missing_evidence_count=context.missing_evidence_count,
            verifier_downgraded=context.verifier_downgraded,
            conflict_count=context.conflict_count,
        )

        decision = BeliefUpdateDecision(
            belief=max(0.0, min(1.0, belief)),
            confidence=0.8,
            rationale="rule_based_belief_update",
        )

        trace = LLMDecisionTrace(
            trace_id=f"trace:{uuid4().hex}",
            decision_point=LLMDecisionPoint.BELIEF_UPDATE,
            mode=LLMDecisionMode.RULE,
            input_payload=context.model_dump(mode="json"),
            parsed_output=decision.model_dump(mode="json"),
            final_output=decision.model_dump(mode="json"),
            status=LLMDecisionStatus.SUCCEEDED,
            created_at=datetime.now(UTC),
        )
        return decision.model_copy(update={"trace_id": trace.trace_id}), trace
