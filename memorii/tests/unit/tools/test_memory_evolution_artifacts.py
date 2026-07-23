from memorii.core.benchmark.artifact_rows import (
    RuntimeExtractorOutput,
    RuntimeExtractorTracePayload,
    RuntimeExtractorTraceRow,
)
from memorii.core.benchmark.reproducibility import build_benchmark_fingerprint
from memorii.core.memory_evolution import (
    ExtractionFailureCode,
    ExtractionRunStatus,
    FallbackOutcome,
    FinalExtractionSource,
    ProviderAttemptStatus,
)
from memorii.tools.benchmark_suites.memory_evolution_artifacts import (
    _system_fingerprint_config,
)


def _trace(*, success: bool) -> RuntimeExtractorTraceRow:
    return RuntimeExtractorTraceRow(
        scenario_id="scenario",
        transition_type="runtime_memory_extraction",
        decision_mode="hybrid",
        effective_decision_mode="hybrid",
        final_output_source="live_llm" if success else "mixed",
        trace=RuntimeExtractorTracePayload(
            provider="openai" if success else "hybrid",
            model="test-model" if success else None,
            prompt_hash="prompt-hash" if success else None,
            scenario_id="scenario",
            call_index=0,
            entity_count=0,
            claim_count=0,
            action_count=0,
        ),
        extraction_status=ExtractionRunStatus.SUCCEEDED,
        provider_attempt_status=(
            ProviderAttemptStatus.SUCCEEDED
            if success
            else ProviderAttemptStatus.PROVIDER_ERROR
        ),
        fallback_outcome=(
            FallbackOutcome.NOT_USED if success else FallbackOutcome.SUCCEEDED
        ),
        final_extraction_source=(
            FinalExtractionSource.PRIMARY if success else FinalExtractionSource.FALLBACK
        ),
        primary_failure_code=None if success else ExtractionFailureCode.PROVIDER_ERROR,
        fallback_provider=None if success else "english_rule",
        output=RuntimeExtractorOutput(),
    )


def test_runtime_system_fingerprint_is_independent_of_observed_outcomes() -> None:
    provider_metadata = {
        "backend": "live_provider",
        "provider": "openai",
        "model": "test-model",
        "timeout_seconds": "60",
        "max_retries": "0",
    }
    common = {
        "mode": "hybrid",
        "source_revision": "revision",
        "source_tree_digest": "a" * 64,
        "runtime_provider_metadata": provider_metadata,
    }

    successful = _system_fingerprint_config(llm_rows=[_trace(success=True)], **common)
    failed = _system_fingerprint_config(llm_rows=[_trace(success=False)], **common)

    assert successful == failed
    assert build_benchmark_fingerprint(successful) == build_benchmark_fingerprint(failed)
    assert successful["provider_metadata"] == provider_metadata
    assert "prompt_contract_refs" not in successful
