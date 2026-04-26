"""Deterministic belief update model for solver overlays."""

from memorii.core.solver.abstention import SolverDecision


def update_solver_belief(
    *,
    prior_belief: float | None,
    decision: SolverDecision,
    evidence_count: int = 0,
    missing_evidence_count: int = 0,
    verifier_downgraded: bool = False,
    conflict_count: int = 0,
) -> float:
    belief = prior_belief if prior_belief is not None else 0.5

    if decision == SolverDecision.SUPPORTED:
        belief += 0.25
    elif decision == SolverDecision.REFUTED:
        belief -= 0.25
    elif decision == SolverDecision.NEEDS_TEST:
        belief -= 0.05
    elif decision == SolverDecision.INSUFFICIENT_EVIDENCE:
        belief -= 0.10
    elif decision == SolverDecision.MULTIPLE_PLAUSIBLE_OPTIONS:
        belief -= 0.05

    belief += min(0.15, max(0, evidence_count) * 0.05)
    belief -= min(0.20, max(0, missing_evidence_count) * 0.05)
    belief -= min(0.20, max(0, conflict_count) * 0.10)

    if verifier_downgraded:
        belief -= 0.20

    return max(0.0, min(1.0, belief))
