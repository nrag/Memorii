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
    prior = prior_belief if prior_belief is not None else 0.5
    positive_evidence_count = max(0, evidence_count)
    unresolved_missing_count = max(0, missing_evidence_count)
    unresolved_conflict_count = max(0, conflict_count)

    raw_belief = (
        prior
        + _decision_delta(decision)
        + _evidence_bonus(positive_evidence_count)
        - _uncertainty_penalty(
            missing_evidence_count=unresolved_missing_count,
            conflict_count=unresolved_conflict_count,
            verifier_downgraded=verifier_downgraded,
        )
    )

    cap = _uncertainty_cap(
        missing_evidence_count=unresolved_missing_count,
        conflict_count=unresolved_conflict_count,
        verifier_downgraded=verifier_downgraded,
    )
    belief = min(raw_belief, cap)

    if decision == SolverDecision.SUPPORTED and positive_evidence_count > 0 and belief <= prior:
        belief = min(prior + 0.05, cap)

    return _clamp_belief(belief)


def _decision_delta(decision: SolverDecision) -> float:
    if decision == SolverDecision.SUPPORTED:
        return 0.25
    if decision == SolverDecision.REFUTED:
        return -0.25
    if decision == SolverDecision.NEEDS_TEST:
        return -0.05
    if decision == SolverDecision.INSUFFICIENT_EVIDENCE:
        return -0.10
    if decision == SolverDecision.MULTIPLE_PLAUSIBLE_OPTIONS:
        return -0.05
    return 0.0


def _evidence_bonus(evidence_count: int) -> float:
    return min(0.10, evidence_count * 0.05)


def _uncertainty_penalty(
    *,
    missing_evidence_count: int,
    conflict_count: int,
    verifier_downgraded: bool,
) -> float:
    missing_penalty = min(0.15, missing_evidence_count * 0.05)
    conflict_penalty = min(0.15, conflict_count * 0.15)
    verifier_penalty = 0.10 if verifier_downgraded else 0.0
    return missing_penalty + conflict_penalty + verifier_penalty


def _uncertainty_cap(
    *,
    missing_evidence_count: int,
    conflict_count: int,
    verifier_downgraded: bool,
) -> float:
    cap = 1.0
    if conflict_count > 0:
        cap = min(cap, 0.80)
    if verifier_downgraded:
        cap = min(cap, 0.75)
    if missing_evidence_count >= 2:
        cap = min(cap, 0.75)
    if missing_evidence_count >= 3:
        cap = min(cap, 0.65)
    return cap


def _clamp_belief(belief: float) -> float:
    return max(0.0, min(1.0, belief))
