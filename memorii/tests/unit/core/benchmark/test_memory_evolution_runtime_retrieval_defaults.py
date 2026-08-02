from __future__ import annotations

from typing import Any

import pytest
from memorii.core.benchmark.memory_evolution_runtime.runner import (
    run_runtime_scenarios,
    runtime_retrieval_invocation,
    validate_runtime_live_safety,
)
from memorii.core.benchmark.memory_evolution_sim import generate_memory_evolution_sim_scenarios
from memorii.core.memory_evolution.operation_models import EvolutionOperationStatus
from memorii.core.prompts.registry import default_prompt_root
from tests.support.memory_evolution_provider_harness import (
    MemoryEvolutionProviderHarness as ProviderMemoryService,
)


def test_runtime_benchmark_requires_explicit_semantic_execution_composition() -> None:
    with pytest.raises(
        RuntimeError,
        match="unavailable in the governed-source admission source-only configuration",
    ):
        run_runtime_scenarios(
            scenarios=[],
            mode="rule",
            dry_run=True,
            allow_live=False,
            prompt_root=default_prompt_root(),
        )


def test_runtime_benchmark_dispatches_checkpoint_retrieval_contract(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    original = ProviderMemoryService.prefetch_result

    def record_call(self: ProviderMemoryService, query: str, **kwargs: Any):
        calls.append(dict(kwargs))
        return original(self, query, **kwargs)

    monkeypatch.setattr(ProviderMemoryService, "prefetch_result", record_call)
    scenarios = generate_memory_evolution_sim_scenarios(
        profile="adversarial",
        scenario_count=10,
        seed=7,
        noise_rate=0.35,
    )

    rows = run_runtime_scenarios(
        scenarios=scenarios,
        mode="llm",
        dry_run=True,
        allow_live=False,
        prompt_root=default_prompt_root(),
        provider_factory=ProviderMemoryService,
    )

    checkpoints = [
        checkpoint
        for scenario in scenarios
        for checkpoint in sorted(scenario.checkpoints, key=lambda item: (item.timestamp, item.checkpoint_id))
    ]
    assert len(calls) == len(checkpoints)
    for checkpoint, call in zip(checkpoints, calls, strict=True):
        invocation = runtime_retrieval_invocation(checkpoint)
        assert call["purpose"] == invocation.purpose
        assert call["include_context"] is invocation.include_context
        assert call["include_conflicts"] is invocation.include_conflicts
        assert call["reference_time"] == checkpoint.timestamp

    calls_by_type = {checkpoint.checkpoint_type: call for checkpoint, call in zip(checkpoints, calls, strict=True)}
    assert calls_by_type["entity_reconstruction"]["purpose"] == "graph_audit"
    assert calls_by_type["claim_rekey"]["purpose"] == "graph_audit"
    assert calls_by_type["entity_split_repair"]["purpose"] == "answer"
    assert calls_by_type["source_trust_conflict"]["purpose"] == "answer"
    assert calls_by_type["belief_ranking"]["purpose"] == "answer"
    assert calls_by_type["execution_continuation"]["purpose"] == "execution"
    assert calls_by_type["modality_suppression"]["purpose"] == "answer"
    assert calls_by_type["modality_suppression"]["include_context"] is True
    assert all(
        row.diagnostics.runtime_retrieval_decision is not None
        and row.diagnostics.runtime_retrieval_decision.query_analysis is not None
        and row.diagnostics.runtime_retrieval_decision.query_analysis.analyzer_path
        == ["english_lexical_query_analyzer"]
        for row in rows.checkpoint_rows
    )
    assert all(row.success for row in rows.checkpoint_rows)
    assert all(not row.diagnostics.runtime_semantic_comparison_issues for row in rows.checkpoint_rows)


def test_dry_runtime_never_constructs_a_live_client() -> None:
    scenario = generate_memory_evolution_sim_scenarios(
        profile="adversarial",
        scenario_count=1,
        seed=7,
        noise_rate=0.35,
    )[0]

    def reject_live_client(*_args: Any, **_kwargs: Any):
        raise AssertionError("dry runtime attempted to construct a live client")

    rows = run_runtime_scenarios(
        scenarios=[scenario],
        mode="llm",
        dry_run=True,
        allow_live=False,
        prompt_root=default_prompt_root(),
        live_client_factory=reject_live_client,
        provider_factory=ProviderMemoryService,
    )

    assert rows.checkpoint_rows
    assert all(row.success for row in rows.checkpoint_rows)


@pytest.mark.parametrize("profile", ["adversarial", "long_horizon"])
def test_known_correct_graph_passes_production_retrieval_and_direct_comparison(
    profile: str,
) -> None:
    scenarios = generate_memory_evolution_sim_scenarios(
        profile=profile,
        scenario_count=10,
        seed=7,
        noise_rate=0.35,
    )

    rows = run_runtime_scenarios(
        scenarios=scenarios,
        mode="llm",
        dry_run=True,
        allow_live=False,
        prompt_root=default_prompt_root(),
        provider_factory=ProviderMemoryService,
    )

    assert len(rows.checkpoint_rows) == sum(len(scenario.checkpoints) for scenario in scenarios)
    assert all(row.success for row in rows.checkpoint_rows)
    assert all(row.diagnostics.runtime_semantic_comparison_issues == [] for row in rows.checkpoint_rows)
    assert all(
        next(stage for stage in row.diagnostics.runtime_stage_trace if stage.stage == "comparison").status == "pass"
        for row in rows.checkpoint_rows
    )


def test_failed_ingestion_prefix_blocks_query_retrieval_and_comparison(monkeypatch) -> None:
    scenario = generate_memory_evolution_sim_scenarios(
        profile="adversarial",
        scenario_count=1,
        seed=7,
        noise_rate=0.35,
    )[0]

    def reject_prefetch(*_args: Any, **_kwargs: Any):
        raise AssertionError("retrieval ran after ingestion validation failed")

    monkeypatch.setattr(ProviderMemoryService, "prefetch_result", reject_prefetch)
    rows = run_runtime_scenarios(
        scenarios=[scenario],
        mode="rule",
        dry_run=True,
        allow_live=False,
        prompt_root=default_prompt_root(),
        provider_factory=ProviderMemoryService,
    )

    assert rows.checkpoint_rows
    assert all(not row.success for row in rows.checkpoint_rows)
    for row in rows.checkpoint_rows:
        assert all(
            not bucket.startswith("production_retrieval_") and bucket != "benchmark_semantic_comparison_missing"
            for bucket in row.runtime_failure_buckets
        )
        downstream = [
            stage
            for stage in row.diagnostics.runtime_stage_trace
            if stage.stage in {"query", "retrieval", "comparison"}
        ]
        assert [stage.status for stage in downstream] == ["not_run", "not_run", "not_run"]


def test_runtime_retrieval_invocation_rejects_unknown_view() -> None:
    scenario = generate_memory_evolution_sim_scenarios(
        profile="adversarial",
        scenario_count=1,
        seed=7,
        noise_rate=0.35,
    )[0]
    invalid = scenario.checkpoints[0].model_copy(update={"required_retrieval_view": "future_view"})

    with pytest.raises(ValueError, match="Unsupported runtime retrieval view"):
        runtime_retrieval_invocation(invalid)


def test_live_runtime_requires_explicit_model_identity(monkeypatch) -> None:
    monkeypatch.setenv("MEMORII_ENV", "test")
    monkeypatch.setenv("MEMORII_SECRET_SOURCE", "process")
    monkeypatch.setenv("MEMORII_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("MEMORII_ENABLE_LIVE_LLM_TESTS", "true")
    monkeypatch.delenv("MEMORII_LLM_MODEL", raising=False)

    with pytest.raises(RuntimeError, match="explicit MEMORII_LLM_MODEL"):
        validate_runtime_live_safety(
            mode="hybrid",
            dry_run=False,
            allow_live=True,
        )


def test_dry_runtime_records_durable_outcome_for_every_extraction() -> None:
    scenario = generate_memory_evolution_sim_scenarios(
        profile="adversarial",
        scenario_count=1,
        seed=7,
        noise_rate=0.35,
    )[0]

    rows = run_runtime_scenarios(
        scenarios=[scenario],
        mode="llm",
        dry_run=True,
        allow_live=False,
        prompt_root=default_prompt_root(),
        provider_factory=ProviderMemoryService,
    )

    assert rows.llm_rows
    assert all(row.operation_status == EvolutionOperationStatus.COMMITTED for row in rows.llm_rows)
    assert all(row.operation_id for row in rows.llm_rows)
