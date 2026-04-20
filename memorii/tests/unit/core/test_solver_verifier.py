from memorii.core.solver import SolverDecision, SolverDecisionVerifier


def test_supported_without_evidence_is_downgraded() -> None:
    verifier = SolverDecisionVerifier()
    outcome = verifier.verify(
        decision=SolverDecision.SUPPORTED,
        evidence_ids=[],
        missing_evidence=[],
        next_best_test=None,
        available_evidence_ids={"ev-1"},
    )

    assert outcome.is_valid is True
    assert outcome.downgraded is True
    assert outcome.final_decision == SolverDecision.INSUFFICIENT_EVIDENCE


def test_insufficient_evidence_without_missing_evidence_is_invalid() -> None:
    verifier = SolverDecisionVerifier()
    outcome = verifier.verify(
        decision=SolverDecision.INSUFFICIENT_EVIDENCE,
        evidence_ids=[],
        missing_evidence=[],
        next_best_test="collect_more_logs",
        available_evidence_ids=set(),
    )

    assert outcome.is_valid is False
    assert outcome.downgraded is False
    assert outcome.final_decision == SolverDecision.INSUFFICIENT_EVIDENCE


def test_needs_test_without_next_best_test_is_invalid() -> None:
    verifier = SolverDecisionVerifier()
    outcome = verifier.verify(
        decision=SolverDecision.NEEDS_TEST,
        evidence_ids=[],
        missing_evidence=["traceback"],
        next_best_test=None,
        available_evidence_ids=set(),
    )

    assert outcome.is_valid is False
    assert outcome.downgraded is False
    assert outcome.final_decision == SolverDecision.INSUFFICIENT_EVIDENCE
