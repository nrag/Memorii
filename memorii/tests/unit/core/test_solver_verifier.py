from memorii.core.solver.abstention import SolverDecision
from memorii.core.solver.models import NextTestAction
from memorii.core.solver.verifier import SolverDecisionVerifier


def test_supported_without_evidence_is_downgraded() -> None:
    verifier = SolverDecisionVerifier()
    outcome = verifier.verify(
        decision=SolverDecision.SUPPORTED,
        evidence_ids=[],
        missing_evidence=[],
        next_test_action=None,
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
        next_test_action=None,
        available_evidence_ids=set(),
    )

    assert outcome.is_valid is False
    assert outcome.downgraded is False
    assert outcome.final_decision == SolverDecision.INSUFFICIENT_EVIDENCE


def test_needs_test_without_structured_action_is_invalid() -> None:
    verifier = SolverDecisionVerifier()
    outcome = verifier.verify(
        decision=SolverDecision.NEEDS_TEST,
        evidence_ids=[],
        missing_evidence=["traceback"],
        next_test_action=None,
        available_evidence_ids=set(),
    )

    assert outcome.is_valid is False
    assert outcome.downgraded is False
    assert outcome.final_decision == SolverDecision.INSUFFICIENT_EVIDENCE


def test_needs_test_with_structured_action_is_valid() -> None:
    verifier = SolverDecisionVerifier()
    outcome = verifier.verify(
        decision=SolverDecision.NEEDS_TEST,
        evidence_ids=[],
        missing_evidence=["traceback"],
        next_test_action=NextTestAction(action_type="inspect_file", description="Inspect failing test file"),
        available_evidence_ids=set(),
    )

    assert outcome.is_valid is True
    assert outcome.downgraded is False
    assert outcome.final_decision == SolverDecision.NEEDS_TEST
