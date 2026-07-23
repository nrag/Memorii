from __future__ import annotations

from datetime import UTC, datetime

import pytest
from memorii.core.benchmark.artifact_rows import SimLLMTraceRow
from memorii.core.benchmark.memory_evolution_sim import SimSystemOutput
from memorii.core.llm_decision.models import (
    LLMDecisionMode,
    LLMDecisionPoint,
    LLMDecisionStatus,
    LLMDecisionTrace,
)
from memorii.core.memory_evolution import FallbackOutcome, ProviderAttemptStatus
from pydantic import ValidationError


def _trace(status: LLMDecisionStatus) -> LLMDecisionTrace:
    return LLMDecisionTrace(
        trace_id="trace:test",
        decision_point=LLMDecisionPoint.MEMORY_EVOLUTION_SIM_RECONSTRUCTION,
        mode=LLMDecisionMode.LLM,
        input_payload={},
        final_output={"operation": "abstain", "rationale": "test"},
        status=status,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _row(**updates: object) -> SimLLMTraceRow:
    values: dict[str, object] = {
        "scenario_id": "scenario:test",
        "checkpoint_id": "checkpoint:test",
        "transition_type": "memory_evolution_sim_reconstruction",
        "decision_mode": "llm",
        "effective_decision_mode": "llm",
        "final_output_source": "fake_oracle",
        "trace": _trace(LLMDecisionStatus.SUCCEEDED),
        "provider_attempt_status": ProviderAttemptStatus.SUCCEEDED,
        "semantic_validation_status": "passed",
        "fallback_outcome": FallbackOutcome.NOT_USED,
        "primary_output_accepted": True,
        "failure_mode": None,
        "output": SimSystemOutput(operation="abstain", rationale="test"),
    }
    values.update(updates)
    return SimLLMTraceRow.model_validate(values)


def test_semantic_id_failure_remains_provider_success_without_fallback() -> None:
    row = _row(
        final_output_source="live_llm",
        trace=_trace(LLMDecisionStatus.VALIDATION_FAILED),
        semantic_validation_status="failed",
        primary_output_accepted=False,
        failure_mode="llm_output_referenced_invalid_ids",
    )

    assert row.provider_attempt_status == ProviderAttemptStatus.SUCCEEDED
    assert row.semantic_validation_status == "failed"
    assert row.fallback_outcome == FallbackOutcome.NOT_USED
    assert row.primary_output_accepted is False


@pytest.mark.parametrize(
    "provider_status",
    [
        ProviderAttemptStatus.PROVIDER_ERROR,
        ProviderAttemptStatus.INVALID_JSON,
        ProviderAttemptStatus.SCHEMA_ERROR,
    ],
)
def test_transport_failure_keeps_semantic_validation_not_evaluated(
    provider_status: ProviderAttemptStatus,
) -> None:
    row = _row(
        final_output_source="rule",
        trace=_trace(LLMDecisionStatus.FALLBACK_USED),
        provider_attempt_status=provider_status,
        semantic_validation_status="not_evaluated",
        fallback_outcome=FallbackOutcome.SUCCEEDED,
        primary_output_accepted=False,
        failure_mode=provider_status.value,
    )

    assert row.semantic_validation_status == "not_evaluated"
    assert row.fallback_outcome == FallbackOutcome.SUCCEEDED


def test_outcome_contract_rejects_semantic_failure_masquerading_as_acceptance() -> None:
    with pytest.raises(ValidationError, match="accepted outputs require"):
        _row(
            semantic_validation_status="failed",
            primary_output_accepted=True,
        )


def test_outcome_contract_rejects_fallback_with_live_final_source() -> None:
    with pytest.raises(ValidationError, match="fallback traces must identify rule"):
        _row(
            final_output_source="live_llm",
            trace=_trace(LLMDecisionStatus.FALLBACK_USED),
            provider_attempt_status=ProviderAttemptStatus.PROVIDER_ERROR,
            semantic_validation_status="not_evaluated",
            fallback_outcome=FallbackOutcome.SUCCEEDED,
            primary_output_accepted=False,
            failure_mode="provider_error",
        )
