from __future__ import annotations

from typing import Any

import pytest
from memorii.core.benchmark.memory_evolution_runtime.runner import (
    run_runtime_scenarios,
    runtime_retrieval_invocation,
)
from memorii.core.benchmark.memory_evolution_sim import generate_memory_evolution_sim_scenarios
from memorii.core.memory_evolution.operation_models import EvolutionOperationStatus
from memorii.core.prompts.registry import default_prompt_root
from memorii.core.provider.service import ProviderMemoryService


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

    run_runtime_scenarios(
        scenarios=scenarios,
        mode="rule",
        dry_run=True,
        allow_live=False,
        prompt_root=default_prompt_root(),
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

    calls_by_type = {
        checkpoint.checkpoint_type: call for checkpoint, call in zip(checkpoints, calls, strict=True)
    }
    assert calls_by_type["entity_split_repair"]["purpose"] == "graph_audit"
    assert calls_by_type["belief_ranking"]["purpose"] == "graph_audit"
    assert calls_by_type["execution_continuation"]["purpose"] == "execution"
    assert calls_by_type["modality_suppression"]["purpose"] == "answer"
    assert calls_by_type["modality_suppression"]["include_context"] is True


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
    )

    assert rows.llm_rows
    assert all(
        row.operation_status == EvolutionOperationStatus.COMMITTED
        for row in rows.llm_rows
    )
    assert all(row.operation_id for row in rows.llm_rows)
