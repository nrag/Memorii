from __future__ import annotations

from typing import Any

from memorii.core.benchmark.memory_evolution_runtime.runner import run_runtime_scenarios
from memorii.core.benchmark.memory_evolution_sim import generate_memory_evolution_sim_scenarios
from memorii.core.prompts.registry import default_prompt_root
from memorii.core.provider.service import ProviderMemoryService


def test_runtime_benchmark_preserves_production_retrieval_defaults(monkeypatch) -> None:
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

    graph_audit_scenario = next(
        scenario
        for scenario in scenarios
        if any(checkpoint.checkpoint_type == "entity_reconstruction" for checkpoint in scenario.checkpoints)
    )
    answer_scenario = next(
        scenario
        for scenario in scenarios
        if any(checkpoint.checkpoint_type == "current_truth" for checkpoint in scenario.checkpoints)
    )

    run_runtime_scenarios(
        scenarios=[graph_audit_scenario, answer_scenario],
        mode="rule",
        dry_run=True,
        allow_live=False,
        prompt_root=default_prompt_root(),
    )

    graph_audit_calls = [call for call in calls if call["purpose"] == "graph_audit"]
    answer_calls = [call for call in calls if call["purpose"] == "answer"]
    assert graph_audit_calls
    assert answer_calls
    assert all(call["include_context"] is True for call in graph_audit_calls)
    assert all(call["include_conflicts"] is True for call in graph_audit_calls)
    assert all("include_context" not in call for call in answer_calls)
    assert all("include_conflicts" not in call for call in answer_calls)
