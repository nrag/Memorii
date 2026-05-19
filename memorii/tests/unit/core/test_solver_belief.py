from memorii.core.solver import SolverDecision, update_solver_belief


def test_supported_with_evidence_increases_from_default_prior() -> None:
    belief = update_solver_belief(
        prior_belief=None,
        decision=SolverDecision.SUPPORTED,
        evidence_count=2,
    )
    assert belief > 0.5


def test_refuted_decreases_from_default_prior() -> None:
    belief = update_solver_belief(
        prior_belief=None,
        decision=SolverDecision.REFUTED,
    )
    assert belief < 0.5


def test_insufficient_evidence_decreases_from_default_prior() -> None:
    belief = update_solver_belief(
        prior_belief=None,
        decision=SolverDecision.INSUFFICIENT_EVIDENCE,
    )
    assert belief < 0.5


def test_missing_evidence_penalty_applies() -> None:
    without_missing = update_solver_belief(
        prior_belief=0.5,
        decision=SolverDecision.NEEDS_TEST,
        missing_evidence_count=0,
    )
    with_missing = update_solver_belief(
        prior_belief=0.5,
        decision=SolverDecision.NEEDS_TEST,
        missing_evidence_count=2,
    )
    assert with_missing < without_missing


def test_verifier_downgrade_penalty_applies() -> None:
    normal = update_solver_belief(
        prior_belief=0.5,
        decision=SolverDecision.SUPPORTED,
        evidence_count=1,
        verifier_downgraded=False,
    )
    downgraded = update_solver_belief(
        prior_belief=0.5,
        decision=SolverDecision.SUPPORTED,
        evidence_count=1,
        verifier_downgraded=True,
    )
    assert downgraded < normal


def test_conflicting_supported_evidence_increases_but_caps_belief() -> None:
    belief = update_solver_belief(
        prior_belief=0.6,
        decision=SolverDecision.SUPPORTED,
        evidence_count=2,
        conflict_count=1,
    )

    assert 0.6 < belief <= 0.8


def test_verifier_downgrade_with_conflict_preserves_cautious_supported_increase() -> None:
    belief = update_solver_belief(
        prior_belief=0.6,
        decision=SolverDecision.SUPPORTED,
        evidence_count=2,
        missing_evidence_count=1,
        verifier_downgraded=True,
        conflict_count=1,
    )

    assert 0.6 < belief <= 0.75


def test_many_missing_evidence_caps_overconfidence() -> None:
    belief = update_solver_belief(
        prior_belief=0.7,
        decision=SolverDecision.SUPPORTED,
        evidence_count=5,
        missing_evidence_count=3,
    )

    assert belief <= 0.65


def test_refuted_still_decreases_even_with_evidence() -> None:
    belief = update_solver_belief(
        prior_belief=0.6,
        decision=SolverDecision.REFUTED,
        evidence_count=3,
    )

    assert belief < 0.6


def test_belief_clamps_to_bounds() -> None:
    high = update_solver_belief(
        prior_belief=0.95,
        decision=SolverDecision.SUPPORTED,
        evidence_count=10,
    )
    low = update_solver_belief(
        prior_belief=0.0,
        decision=SolverDecision.REFUTED,
        missing_evidence_count=10,
        verifier_downgraded=True,
        conflict_count=10,
    )
    assert high == 1.0
    assert low == 0.0
