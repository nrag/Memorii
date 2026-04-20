"""Deterministic verification checks for solver outputs."""

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.solver.abstention import SolverDecision


class VerificationOutcome(BaseModel):
    final_decision: SolverDecision
    downgraded: bool = False
    reasons: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class SolverDecisionVerifier:
    """Minimal verifier that enforces evidence-bound commitments."""

    def verify(
        self,
        *,
        decision: SolverDecision,
        evidence_ids: list[str],
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
                    downgraded=True,
                    reasons=reasons,
                )

        return VerificationOutcome(final_decision=decision, downgraded=False, reasons=[])
