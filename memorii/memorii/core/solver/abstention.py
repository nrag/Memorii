"""Abstention-aware solver decision labels and policy helpers."""

from enum import Enum


class SolverDecision(str, Enum):
    SUPPORTED = "SUPPORTED"
    REFUTED = "REFUTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NEEDS_TEST = "NEEDS_TEST"
    MULTIPLE_PLAUSIBLE_OPTIONS = "MULTIPLE_PLAUSIBLE_OPTIONS"


class ConfidenceBand(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


ABSTENTION_DECISIONS: set[SolverDecision] = {
    SolverDecision.INSUFFICIENT_EVIDENCE,
    SolverDecision.NEEDS_TEST,
    SolverDecision.MULTIPLE_PLAUSIBLE_OPTIONS,
}


def requires_commitment(decision: SolverDecision) -> bool:
    return decision in {SolverDecision.SUPPORTED, SolverDecision.REFUTED}
