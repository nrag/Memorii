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


def test_needs_test_requires_next_best_test_or_next_test_action() -> None:
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


def test_needs_test_with_structured_next_test_action_is_valid() -> None:
    parsed = SolverDecisionOutput.model_validate(
        {
            "decision": "NEEDS_TEST",
            "evidence_ids": [],
            "missing_evidence": ["traceback"],
            "next_test_action": {
                "action_type": "run_command",
                "description": "Run targeted test",
                "required_tool": "pytest",
            },
            "rationale_short": "Need executable next step",
            "confidence_band": "low",
        }
    )

    assert parsed.next_best_test is None
    assert parsed.next_test_action is not None
    assert parsed.next_test_action.action_type == "run_command"


def test_invalid_next_test_action_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SolverDecisionOutput.model_validate(
            {
                "decision": "NEEDS_TEST",
                "evidence_ids": [],
                "missing_evidence": ["traceback"],
                "next_test_action": {
                    "action_type": "unknown_action",
                    "description": "Run targeted test",
                },
                "rationale_short": "Need executable next step",
                "confidence_band": "low",
            }
        )
