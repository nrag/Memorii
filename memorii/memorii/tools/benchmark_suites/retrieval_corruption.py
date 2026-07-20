"""Retrieval corruption benchmark suite runner."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from memorii.core.benchmark.fixtures import normalize_fixtures
from memorii.core.benchmark.llm_adapters import LLMRetrievalRelevanceDecisionAdapter
from memorii.core.benchmark.metrics import compute_metrics
from memorii.core.benchmark.models import (
    BenchmarkRunReport,
    BenchmarkScenarioFixture,
    BenchmarkSystem,
    ScenarioResult,
)
from memorii.core.benchmark.retrieval_relevance_decision import (
    retrieval_relevance_assertion_passed,
    retrieval_relevance_context_for_fixture,
    retrieval_relevance_engine_result_from_llm,
    retrieval_relevance_trace_for_rule,
    rule_retrieval_relevance_decision_for_fixture,
)
from memorii.core.env_config import load_memorii_environment
from memorii.core.llm_config import DecisionModeName, LLMDecisionRuntimeConfig, LLMLiveTestConfig, LLMRuntimeConfig
from memorii.core.llm_decision.models import LLMDecisionMode
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.prompts.registry import PromptRegistry
from memorii.tools.benchmark_registry import BenchmarkSuiteRunner
from memorii.tools.benchmark_suites.common import ALL_DECISION_MODES
from memorii.tools.benchmark_suites.fake_adapters import _ExpectedRetrievalRelevanceFakeAdapter
from memorii.tools.benchmark_suites.fixture_harness import (
    FixtureBackedBenchmarkSuiteRunner,
    aggregate_by_category,
    aggregate_by_system,
)
from memorii.tools.benchmark_suites.fixture_loaders import load_retrieval_corruption_fixture_set
from memorii.tools.benchmark_suites.runtime_dependencies import BenchmarkRuntimeDependencies
from memorii.tools.run_live_llm_eval import _validate_live_safety

SUITE_NAME = "retrieval_corruption_v1"


def _decision_mode(mode: str) -> DecisionModeName:
    if mode in {"auto", "rule", "llm", "hybrid"}:
        return cast(DecisionModeName, mode)
    raise ValueError(f"Unsupported retrieval corruption mode: {mode}")


def apply_retrieval_relevance_assertions(
    report: BenchmarkRunReport,
    retrieval_rows: list[dict[str, object]],
) -> BenchmarkRunReport:
    row_by_scenario = {str(row["scenario_id"]): row for row in retrieval_rows}
    updated_results: list[ScenarioResult] = []
    for result in report.scenario_results:
        if result.system != BenchmarkSystem.MEMORII:
            updated_results.append(result)
            continue
        row = row_by_scenario.get(result.scenario_id)
        if row is None:
            updated_results.append(result)
            continue
        relevance_passed = row.get("retrieval_relevance_assertion_passed") is True
        scenario_success = result.observation.scenario_success is True and relevance_passed
        observation = result.observation.model_copy(update={"scenario_success": scenario_success})
        updated_results.append(
            result.model_copy(update={"observation": observation, "metrics": compute_metrics(observation)})
        )
    return report.model_copy(
        update={
            "scenario_results": updated_results,
            "aggregate_by_system": aggregate_by_system(updated_results),
            "aggregate_by_category": aggregate_by_category(updated_results),
        }
    )


def run_retrieval_relevance_decisions(
    fixtures: list[BenchmarkScenarioFixture],
    mode: str,
    dry_run: bool,
    allow_live: bool,
    prompt_root: Path,
    dependencies: BenchmarkRuntimeDependencies,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    env_snapshot = load_memorii_environment()
    runtime_config = LLMRuntimeConfig.from_env(env_snapshot.env)
    decision_config = (
        LLMDecisionRuntimeConfig(mode=_decision_mode(mode))
        if mode != "auto"
        else LLMDecisionRuntimeConfig.from_env(env_snapshot.env)
    )
    effective_mode = decision_config.resolve(runtime_config)
    if effective_mode in {"llm", "hybrid"}:
        live_config = LLMLiveTestConfig.from_env(env_snapshot.env)
        _validate_live_safety(
            modes=[effective_mode],
            dry_run=dry_run,
            allow_live=allow_live,
            runtime_config=runtime_config,
            live_config=live_config,
        )

    registry = PromptRegistry(prompt_root=prompt_root)
    adapter = None
    llm_binding = None
    if effective_mode in {"llm", "hybrid"}:
        llm_binding = dependencies.bind_llm_client(dry_run=dry_run, config=runtime_config)
        runner = PromptLLMRunner(client=llm_binding.client, config=runtime_config)
        adapter = (
            _ExpectedRetrievalRelevanceFakeAdapter(fixtures=fixtures, registry=registry)
            if dependencies.use_oracle_adapters(dry_run=dry_run)
            else LLMRetrievalRelevanceDecisionAdapter(runner=runner, registry=registry)
        )

    rows: list[dict[str, object]] = []
    llm_rows: list[dict[str, object]] = []
    for fixture in normalize_fixtures(fixtures):
        if fixture.retrieval is None:
            continue
        context = retrieval_relevance_context_for_fixture(fixture)
        rule_decision = rule_retrieval_relevance_decision_for_fixture(fixture)
        rule_output = rule_decision.model_dump(mode="json")
        rule_trace = retrieval_relevance_trace_for_rule(
            context=context,
            decision=rule_decision,
            mode="rule",
        )
        request_id = f"retrieval_relevance:{mode}:{fixture.scenario_id}"
        output = rule_output
        llm_success = False
        llm_used = False
        fallback_used = effective_mode in {"auto", "hybrid"} and effective_mode == "rule"
        fallback_reason = "llm_not_configured" if fallback_used else None
        final_output_source = "rule"

        if effective_mode in {"llm", "hybrid"} and adapter is not None:
            llm_used = True
            metadata: dict[str, object] = {
                "suite": SUITE_NAME,
                "scenario_id": fixture.scenario_id,
                "decision_mode": mode,
                "transition_type": "retrieval_relevance",
            }
            llm_result = adapter.decide(
                context,
                request_id=request_id,
                metadata=metadata,
            )
            output, llm_trace, llm_success, fallback_reason = retrieval_relevance_engine_result_from_llm(
                result=llm_result,
                mode=LLMDecisionMode(effective_mode),
                rule_output=rule_output,
            )
            if llm_success:
                if llm_binding is None:
                    raise RuntimeError("LLM result is missing execution provenance")
                final_output_source = llm_binding.final_output_source
            else:
                final_output_source = "rule"
            llm_rows.append(
                {
                    "scenario_id": fixture.scenario_id,
                    "transition_type": "retrieval_relevance",
                    "decision_mode": mode,
                    "effective_decision_mode": effective_mode,
                    "trace": llm_trace.model_dump(mode="json"),
                    "success": llm_success,
                    "fallback_used": not llm_success,
                    "failure_mode": fallback_reason,
                    "output": output,
                }
            )
        else:
            llm_trace = rule_trace

        assertion_passed = retrieval_relevance_assertion_passed(fixture=fixture, decision=output)
        success = assertion_passed and (effective_mode != "llm" or llm_success or not llm_used)
        rows.append(
            {
                "scenario_id": fixture.scenario_id,
                "transition_type": "retrieval_relevance",
                "decision_mode": mode,
                "effective_decision_mode": effective_mode,
                "llm_call_made": llm_used,
                "fallback_used": (effective_mode in {"auto", "hybrid"} and not llm_success)
                if llm_used
                else fallback_used,
                "fallback_reason": fallback_reason,
                "final_output_source": final_output_source,
                "request_id": request_id if llm_used else llm_trace.trace_id,
                "success": success,
                "failure_mode": None if success else (fallback_reason or "retrieval_relevance_assertion_failed"),
                "transition_assertion_passed": assertion_passed,
                "retrieval_relevance_assertion_passed": assertion_passed,
                "output": output,
            }
        )
    return rows, llm_rows


def build_runner(*, dependencies: BenchmarkRuntimeDependencies) -> BenchmarkSuiteRunner:
    return FixtureBackedBenchmarkSuiteRunner(
        suite_name=SUITE_NAME,
        loader=load_retrieval_corruption_fixture_set,
        supported_modes=ALL_DECISION_MODES,
        dependencies=dependencies,
        trace_runner=run_retrieval_relevance_decisions,
        report_mutator=apply_retrieval_relevance_assertions,
        trace_artifact_name="retrieval_relevance_traces.jsonl",
    )
