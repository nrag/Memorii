"""Deterministic verification checks for solver outputs."""

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.solver.abstention import SolverDecision


class VerificationOutcome(BaseModel):
    final_decision: SolverDecision
    is_valid: bool = True
    downgraded: bool = False
    reasons: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class SolverDecisionVerifier:
    """Deterministic verifier that enforces commitment and unresolved-state invariants."""

    def verify(
        self,
        *,
        decision: SolverDecision,
        evidence_ids: list[str],
        missing_evidence: list[str],
        next_best_test: str | None,
        available_evidence_ids: set[str],
    ) -> VerificationOutcome:
        reasons: list[str] = []

        if decision in {SolverDecision.SUPPORTED, SolverDecision.REFUTED}:
            if not evidence_ids:
                reasons.append("missing_evidence_ids_for_commitment")
            else:
                missing = [item for item in evidence_ids if item not in available_evidence_ids]
                if missing:
                    reasons.append(f"unknown_evidence_ids:{','.join(sorted(missing))}")

            if reasons:
                return VerificationOutcome(
                    final_decision=SolverDecision.INSUFFICIENT_EVIDENCE,
                    is_valid=True,
                    downgraded=True,
                    reasons=reasons,
                )
        elif decision == SolverDecision.NEEDS_TEST:
            if not missing_evidence:
                reasons.append("needs_test_missing_missing_evidence")
            if next_best_test is None or not next_best_test.strip():
                reasons.append("needs_test_missing_next_best_test")
        elif decision == SolverDecision.INSUFFICIENT_EVIDENCE:
            if not missing_evidence:
                reasons.append("insufficient_evidence_missing_missing_evidence")

        if reasons:
            return VerificationOutcome(
                final_decision=SolverDecision.INSUFFICIENT_EVIDENCE,
                is_valid=False,
                downgraded=False,
                reasons=reasons,
            )

        return VerificationOutcome(final_decision=decision, is_valid=True, downgraded=False, reasons=[])
