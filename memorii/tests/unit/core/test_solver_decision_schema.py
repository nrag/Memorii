import pytest
from pydantic import ValidationError

from memorii.core.solver import SolverDecisionOutput


def test_confidence_band_is_enum() -> None:
    parsed = SolverDecisionOutput.model_validate(
        {
            "decision": "SUPPORTED",
            "evidence_ids": ["ev-1"],
            "missing_evidence": [],
            "next_best_test": None,
            "rationale_short": "grounded",
            "confidence_band": "high",
        }
    )

    assert parsed.confidence_band.value == "high"


def test_supported_requires_evidence_ids() -> None:
    with pytest.raises(ValidationError):
        SolverDecisionOutput.model_validate(
            {
                "decision": "SUPPORTED",
                "evidence_ids": [],
                "missing_evidence": [],
                "next_best_test": None,
                "rationale_short": "unsupported",
                "confidence_band": "medium",
            }
        )


def test_insufficient_evidence_requires_missing_evidence() -> None:
    with pytest.raises(ValidationError):
        SolverDecisionOutput.model_validate(
            {
                "decision": "INSUFFICIENT_EVIDENCE",
                "evidence_ids": [],
                "missing_evidence": [],
                "next_best_test": None,
                "rationale_short": "no gap list",
                "confidence_band": "low",
            }
        )


def test_needs_test_requires_next_best_test() -> None:
    with pytest.raises(ValidationError):
        SolverDecisionOutput.model_validate(
            {
                "decision": "NEEDS_TEST",
                "evidence_ids": [],
                "missing_evidence": ["traceback"],
                "next_best_test": None,
                "rationale_short": "must provide next test",
                "confidence_band": "low",
            }
        )
