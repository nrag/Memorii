from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from memorii.core.belief.models import BeliefUpdateContext
from memorii.core.belief.rule_provider import RuleBasedBeliefUpdateProvider
from memorii.core.benchmark.execution_graph_decision import (
    ExecutionGraphDecisionContext,
    ExecutionGraphScenario,
    execution_graph_assertion_passed,
    execution_graph_context_for_scenario,
    execution_graph_engine_result_from_llm,
    execution_graph_trace_for_rule,
    expected_execution_graph_decision_for_scenario,
    fake_llm_result_for_execution_graph,
    rule_execution_graph_decision_for_scenario,
)
from memorii.core.benchmark.lifecycle_decision import (
    LifecycleDecisionContext,
    expected_lifecycle_decision_for_fixture,
    fake_llm_result_for_lifecycle,
    lifecycle_assertion_passed,
    lifecycle_context_for_fixture,
    lifecycle_engine_result_from_llm,
    lifecycle_family_requires_decision,
    lifecycle_trace_for_rule,
    rule_lifecycle_decision_for_fixture,
)
from memorii.core.benchmark.retrieval_relevance_decision import (
    RetrievalRelevanceContext,
    expected_retrieval_relevance_decision_for_fixture,
    fake_llm_result_for_retrieval_relevance,
    retrieval_relevance_assertion_passed,
    retrieval_relevance_context_for_fixture,
    retrieval_relevance_engine_result_from_llm,
    retrieval_relevance_trace_for_rule,
    rule_retrieval_relevance_decision_for_fixture,
)
from memorii.core.benchmark.fixtures import normalize_fixtures
from memorii.core.benchmark.harness import BenchmarkHarness
from memorii.core.benchmark.metrics import aggregate_metrics, compute_metrics
from memorii.core.benchmark.models import (
    BenchmarkRunConfig,
    BenchmarkRunReport,
    BenchmarkScenarioFixture,
    BenchmarkSystem,
    MemoryLifecycleFamily,
    ScenarioResult,
)
from memorii.core.benchmark.reporting import write_artifacts
from memorii.core.benchmark.reproducibility import apply_seed, build_run_id
from memorii.core.benchmark.scenarios import ScenarioExecutor
from memorii.core.benchmark.validation import validate_preflight, validate_report
from memorii.core.env_config import load_memorii_environment
from memorii.core.llm_config import LLMDecisionRuntimeConfig, LLMLiveTestConfig, LLMRuntimeConfig
from memorii.core.llm_decision.adapters import (
    LLMExecutionGraphDecisionAdapter,
    LLMBeliefUpdateAdapter,
    LLMLifecycleDecisionAdapter,
    LLMPromotionDecisionAdapter,
    LLMRetrievalRelevanceDecisionAdapter,
)
from memorii.core.llm_decision.models import LLMDecisionMode
from memorii.core.llm_provider.models import LLMDecisionResult, LLMStructuredRequest
from memorii.core.llm_eval.engine_result import DecisionEngineResult
from memorii.core.llm_eval.runner import BeliefUpdateEngine, PromotionDecisionEngine
from memorii.core.llm_provider.factory import LLMClientFactory
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.prompts.registry import PromptRegistry
from memorii.core.promotion.models import PromotionCandidateType, PromotionContext
from memorii.core.promotion.rule_provider import RuleBasedPromotionDecisionProvider
from memorii.core.solver.abstention import SolverDecision
from memorii.tools.run_live_llm_eval import EvalFakeClient, _validate_live_safety
from tests.fixtures.benchmarks.benchmark_minimal import load_benchmark_fixture_set
from tests.fixtures.benchmarks.execution_graph_v1 import load_execution_graph_v1_fixture_set
from tests.fixtures.benchmarks.memory_lifecycle_v1 import load_memory_lifecycle_v1_fixture_set
from tests.fixtures.benchmarks.retrieval_corruption_v1 import load_retrieval_corruption_v1_fixture_set

_DEFAULT_EVAL_FAKE_CLIENT = EvalFakeClient


def _load_suite(suite: str) -> tuple[list[BenchmarkScenarioFixture], str]:
    if suite == "memory_lifecycle_v1":
        return (
            load_memory_lifecycle_v1_fixture_set(),
            "tests/fixtures/benchmarks/memory_lifecycle_v1.py",
        )
    if suite == "retrieval_corruption_v1":
        return (
            load_retrieval_corruption_v1_fixture_set(),
            "tests/fixtures/benchmarks/retrieval_corruption_v1.py",
        )
    if suite == "minimal":
        return (
            load_benchmark_fixture_set(),
            "tests/fixtures/benchmarks/benchmark_minimal.py",
        )
    raise ValueError(f"Unsupported benchmark suite: {suite}")


def _load_execution_graph_suite(suite: str) -> tuple[list[ExecutionGraphScenario], str]:
    if suite == "execution_graph_v1":
        return (
            load_execution_graph_v1_fixture_set(),
            "tests/fixtures/benchmarks/execution_graph_v1.py",
        )
    raise ValueError(f"Unsupported execution graph benchmark suite: {suite}")


def _aggregate_by_system(results: list[ScenarioResult]) -> dict[BenchmarkSystem, object]:
    grouped: dict[BenchmarkSystem, list[object]] = {}
    for result in results:
        grouped.setdefault(result.system, []).append(result.observation)
    return {system: aggregate_metrics(observations) for system, observations in grouped.items()}


def _aggregate_by_category(results: list[ScenarioResult]) -> dict[object, dict[BenchmarkSystem, object]]:
    grouped: dict[object, dict[BenchmarkSystem, list[object]]] = {}
    for result in results:
        grouped.setdefault(result.category, {})
        grouped[result.category].setdefault(result.system, []).append(result.observation)
    return {
        category: {
            system: aggregate_metrics(observations)
            for system, observations in by_system.items()
        }
        for category, by_system in grouped.items()
    }


def _run_memorii_only(
    *,
    fixtures: list[BenchmarkScenarioFixture],
    config: BenchmarkRunConfig,
) -> BenchmarkRunReport:
    apply_seed(config.seed)
    normalized = normalize_fixtures(fixtures)
    validate_preflight(fixtures=normalized, config=config)
    executor = ScenarioExecutor()

    results: list[ScenarioResult] = []
    for fixture in normalized:
        observation = executor.run(fixture=fixture, system=BenchmarkSystem.MEMORII)
        results.append(
            ScenarioResult(
                scenario_id=fixture.scenario_id,
                category=fixture.category,
                system=BenchmarkSystem.MEMORII,
                observation=observation,
                metrics=compute_metrics(observation),
            )
        )

    report = BenchmarkRunReport(
        run_id=build_run_id(config=config, fixtures=normalized),
        generated_at=datetime.now(UTC),
        config=config,
        scenario_results=results,
        aggregate_by_system=_aggregate_by_system(results),
        aggregate_by_category=_aggregate_by_category(results),
        baseline_comparison={},
    )
    validate_report(report)
    return report


def _promotion_context_for_fixture(fixture: BenchmarkScenarioFixture) -> PromotionContext:
    family = fixture.lifecycle.family if fixture.lifecycle is not None else None
    explicit_user_memory_request = family == MemoryLifecycleFamily.CREATE_AND_REUSE_USER_PREFERENCE
    repeated_across_episodes = 3 if family == MemoryLifecycleFamily.PROMOTE_REPEATED_PROJECT_FACT else 0
    if family == MemoryLifecycleFamily.CREATE_AND_REUSE_USER_PREFERENCE:
        candidate_type = PromotionCandidateType.USER_MEMORY
        content = "User explicitly said they prefer concise coding answers."
    elif family == MemoryLifecycleFamily.PROMOTE_REPEATED_PROJECT_FACT:
        candidate_type = PromotionCandidateType.PROJECT_FACT
        content = "Project release freeze repeats across recent sprint episodes."
    elif family == MemoryLifecycleFamily.BLOCK_INFERRED_USER_PREFERENCE:
        candidate_type = PromotionCandidateType.USER_MEMORY
        content = "User asked for concise output once; do not infer a durable global preference."
    elif family == MemoryLifecycleFamily.MERGE_NEAR_DUPLICATE_PREFERENCE:
        candidate_type = PromotionCandidateType.USER_MEMORY
        content = "Near-duplicate concise direct answer preference should merge with existing memory."
    elif family == MemoryLifecycleFamily.MERGE_WITH_PROVENANCE_LINK:
        candidate_type = PromotionCandidateType.USER_MEMORY
        content = "Duplicate review-style preference should link provenance to the existing memory instead of creating a new one."
    elif family == MemoryLifecycleFamily.TASK_SCOPED_DOES_NOT_OVERWRITE_GLOBAL:
        candidate_type = PromotionCandidateType.USER_MEMORY
        content = "Task-only verbose review preference for PR 84 should not overwrite the global concise review preference."
    else:
        candidate_type = PromotionCandidateType.SEMANTIC
        content = f"Lifecycle transition candidate for {fixture.scenario_id}."

    related_memory_ids = []
    if family in {
        MemoryLifecycleFamily.MERGE_NEAR_DUPLICATE_PREFERENCE,
        MemoryLifecycleFamily.MERGE_WITH_PROVENANCE_LINK,
        MemoryLifecycleFamily.SUPERSEDE_CORRECTED_PREFERENCE,
        MemoryLifecycleFamily.SUPERSEDE_STALE_PROJECT_FACT,
        MemoryLifecycleFamily.RETRIEVAL_AFTER_EXPIRATION,
    } and fixture.lifecycle is not None:
        related_memory_ids = list(fixture.lifecycle.expected_active_memory_ids)

    return PromotionContext(
        candidate_id=f"lifecycle:{fixture.scenario_id}:promotion",
        candidate_type=candidate_type,
        content=content,
        source_ids=[fixture.scenario_id],
        related_memory_ids=related_memory_ids,
        repeated_across_episodes=repeated_across_episodes,
        explicit_user_memory_request=explicit_user_memory_request,
        created_from="lifecycle_benchmark",
        metadata={
            "scenario_id": fixture.scenario_id,
            "lifecycle_family": family.value if family is not None else None,
        },
    )


def _belief_context_for_fixture(fixture: BenchmarkScenarioFixture) -> BeliefUpdateContext:
    family = fixture.lifecycle.family if fixture.lifecycle is not None else None
    conflict_count = 1 if family in {
        MemoryLifecycleFamily.SUPERSEDE_CORRECTED_PREFERENCE,
        MemoryLifecycleFamily.SUPERSEDE_STALE_PROJECT_FACT,
        MemoryLifecycleFamily.RETRIEVAL_AFTER_EXPIRATION,
        MemoryLifecycleFamily.AVOID_WRONG_ENTITY_CARRYOVER,
        MemoryLifecycleFamily.SOURCE_TRUST_CONFLICT,
        MemoryLifecycleFamily.EXPIRE_AND_ARCHIVE_OVER_TIME,
        MemoryLifecycleFamily.MULTI_EVENT_CREATE_UPDATE_INVALIDATE_RETRIEVE,
    } else 0
    decision = SolverDecision.INSUFFICIENT_EVIDENCE if family in {
        MemoryLifecycleFamily.BLOCK_INFERRED_USER_PREFERENCE,
        MemoryLifecycleFamily.AVOID_WRONG_ENTITY_CARRYOVER,
    } else SolverDecision.SUPPORTED
    if family == MemoryLifecycleFamily.BELIEF_DEPENDENCY_INVALIDATION:
        decision = SolverDecision.REFUTED
        conflict_count = 0
    evidence_count = 2 if decision == SolverDecision.SUPPORTED else 0
    if family == MemoryLifecycleFamily.BELIEF_DEPENDENCY_INVALIDATION:
        evidence_count = 2
    return BeliefUpdateContext(
        prior_belief=0.8 if family == MemoryLifecycleFamily.BELIEF_DEPENDENCY_INVALIDATION else 0.5,
        decision=decision,
        evidence_count=evidence_count,
        missing_evidence_count=1 if decision == SolverDecision.INSUFFICIENT_EVIDENCE else 0,
        conflict_count=conflict_count,
        evidence_ids=[fixture.scenario_id],
        node_id=f"lifecycle:{fixture.scenario_id}:belief",
        solver_run_id="solver:lifecycle:v1",
        metadata={
            "scenario_id": fixture.scenario_id,
            "lifecycle_family": family.value if family is not None else None,
        },
    )


def _transition_kind(fixture: BenchmarkScenarioFixture) -> str:
    family = fixture.lifecycle.family if fixture.lifecycle is not None else None
    if fixture.lifecycle is not None and fixture.lifecycle.require_lifecycle_decision:
        return "lifecycle_decision"
    if lifecycle_family_requires_decision(family):
        return "lifecycle_decision"
    if family in {
        MemoryLifecycleFamily.CREATE_AND_REUSE_USER_PREFERENCE,
        MemoryLifecycleFamily.BLOCK_INFERRED_USER_PREFERENCE,
        MemoryLifecycleFamily.MERGE_NEAR_DUPLICATE_PREFERENCE,
        MemoryLifecycleFamily.MERGE_WITH_PROVENANCE_LINK,
        MemoryLifecycleFamily.PROMOTE_REPEATED_PROJECT_FACT,
        MemoryLifecycleFamily.PRESERVE_TASK_SCOPED_PREFERENCE,
        MemoryLifecycleFamily.TASK_SCOPED_DOES_NOT_OVERWRITE_GLOBAL,
    }:
        return "promotion"
    return "belief_update"


def _transition_assertion_passed(
    *,
    fixture: BenchmarkScenarioFixture,
    kind: str,
    decision: dict[str, object],
) -> bool:
    if kind == "promotion":
        promote = decision.get("promote")
        if not isinstance(promote, bool):
            return False
        family = fixture.lifecycle.family if fixture.lifecycle is not None else None
        if family in {
            MemoryLifecycleFamily.CREATE_AND_REUSE_USER_PREFERENCE,
            MemoryLifecycleFamily.PROMOTE_REPEATED_PROJECT_FACT,
        }:
            return promote is True
        if family in {
            MemoryLifecycleFamily.BLOCK_INFERRED_USER_PREFERENCE,
            MemoryLifecycleFamily.MERGE_NEAR_DUPLICATE_PREFERENCE,
            MemoryLifecycleFamily.MERGE_WITH_PROVENANCE_LINK,
            MemoryLifecycleFamily.PRESERVE_TASK_SCOPED_PREFERENCE,
            MemoryLifecycleFamily.TASK_SCOPED_DOES_NOT_OVERWRITE_GLOBAL,
        }:
            return promote is False
        return True
    if kind == "lifecycle_decision":
        return lifecycle_assertion_passed(fixture=fixture, decision=decision)
    belief = decision.get("belief")
    if not isinstance(belief, int | float) or not 0.0 <= float(belief) <= 1.0:
        return False
    family = fixture.lifecycle.family if fixture.lifecycle is not None else None
    if family == MemoryLifecycleFamily.BELIEF_DEPENDENCY_INVALIDATION:
        return float(belief) <= 0.65
    return True


def _apply_transition_assertions(
    *,
    report: BenchmarkRunReport,
    transition_rows: list[dict[str, object]],
) -> BenchmarkRunReport:
    transition_by_scenario = {str(row["scenario_id"]): row for row in transition_rows}
    updated_results: list[ScenarioResult] = []
    for result in report.scenario_results:
        row = transition_by_scenario.get(result.scenario_id)
        if row is None:
            updated_results.append(result)
            continue
        transition_passed = row.get("transition_assertion_passed") is True
        if row.get("transition_type") == "lifecycle_decision":
            lifecycle_success = transition_passed
            scenario_success = transition_passed
        else:
            lifecycle_success = result.observation.lifecycle_success is True and transition_passed
            scenario_success = result.observation.scenario_success is True and transition_passed
        observation = result.observation.model_copy(
            update={
                "lifecycle_success": lifecycle_success,
                "scenario_success": scenario_success,
            }
        )
        updated_results.append(
            result.model_copy(update={"observation": observation, "metrics": compute_metrics(observation)})
        )
    return report.model_copy(
        update={
            "scenario_results": updated_results,
            "aggregate_by_system": _aggregate_by_system(updated_results),
            "aggregate_by_category": _aggregate_by_category(updated_results),
        }
    )


def _apply_retrieval_relevance_assertions(
    *,
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
            "aggregate_by_system": _aggregate_by_system(updated_results),
            "aggregate_by_category": _aggregate_by_category(updated_results),
        }
    )


def _run_rule_lifecycle_transitions(
    *,
    fixtures: list[BenchmarkScenarioFixture],
    mode: str,
) -> list[dict[str, object]]:
    promotion_rule = RuleBasedPromotionDecisionProvider()
    belief_rule = RuleBasedBeliefUpdateProvider()
    lifecycle_rows: list[dict[str, object]] = []
    for fixture in normalize_fixtures(fixtures):
        kind = _transition_kind(fixture)
        if kind == "promotion":
            decision, trace = promotion_rule.decide(context=_promotion_context_for_fixture(fixture))
            output = decision.model_dump(mode="json")
        elif kind == "lifecycle_decision":
            context = lifecycle_context_for_fixture(fixture)
            decision = rule_lifecycle_decision_for_fixture(fixture)
            trace = lifecycle_trace_for_rule(context=context, decision=decision, mode="rule")
            output = decision.model_dump(mode="json")
        else:
            decision, trace = belief_rule.update(context=_belief_context_for_fixture(fixture))
            output = decision.model_dump(mode="json")
        transition_assertion_passed = _transition_assertion_passed(
            fixture=fixture,
            kind=kind,
            decision=output,
        )
        lifecycle_rows.append(
            {
                "scenario_id": fixture.scenario_id,
                "transition_type": kind,
                "decision_mode": mode,
                "effective_decision_mode": "rule",
                "llm_call_made": False,
                "fallback_used": mode in {"auto", "hybrid"},
                "fallback_reason": "llm_not_configured" if mode in {"auto", "hybrid"} else None,
                "final_output_source": "rule",
                "request_id": trace.trace_id,
                "success": transition_assertion_passed,
                "failure_mode": None if transition_assertion_passed else "transition_assertion_failed",
                "transition_assertion_passed": transition_assertion_passed,
                "lifecycle_assertion_passed": transition_assertion_passed,
                "output": output,
            }
        )
    return lifecycle_rows


def _run_lifecycle_transitions(
    *,
    fixtures: list[BenchmarkScenarioFixture],
    mode: str,
    dry_run: bool,
    allow_live: bool,
    prompt_root: Path,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    env_snapshot = load_memorii_environment()
    runtime_config = LLMRuntimeConfig.from_env(env_snapshot.env)
    decision_config = LLMDecisionRuntimeConfig(mode=mode) if mode != "auto" else LLMDecisionRuntimeConfig.from_env(env_snapshot.env)
    effective_mode = decision_config.resolve(runtime_config)
    if effective_mode == "rule":
        return _run_rule_lifecycle_transitions(fixtures=fixtures, mode=mode), []

    live_config = LLMLiveTestConfig.from_env(env_snapshot.env)
    if effective_mode in {"llm", "hybrid"}:
        _validate_live_safety(
            modes=[effective_mode],
            dry_run=dry_run,
            allow_live=allow_live,
            runtime_config=runtime_config,
            live_config=live_config,
        )

    client = EvalFakeClient() if dry_run else LLMClientFactory.from_config(runtime_config)
    runner = PromptLLMRunner(client=client, config=runtime_config)
    registry = PromptRegistry(prompt_root=prompt_root)
    promotion_adapter = LLMPromotionDecisionAdapter(runner=runner, registry=registry)
    belief_adapter = LLMBeliefUpdateAdapter(runner=runner, registry=registry)
    lifecycle_adapter = (
        _ExpectedLifecycleFakeAdapter(fixtures=fixtures, registry=registry)
        if dry_run and EvalFakeClient is _DEFAULT_EVAL_FAKE_CLIENT
        else LLMLifecycleDecisionAdapter(runner=runner, registry=registry)
    )
    promotion_engine = PromotionDecisionEngine(
        rule_engine=RuleBasedPromotionDecisionProvider(),
        llm_adapter=promotion_adapter,
        mode=LLMDecisionMode(effective_mode),
    )
    belief_engine = BeliefUpdateEngine(
        rule_engine=RuleBasedBeliefUpdateProvider(),
        llm_adapter=belief_adapter,
        mode=LLMDecisionMode(effective_mode),
    )

    lifecycle_rows = []
    llm_rows = []
    for fixture in normalize_fixtures(fixtures):
        kind = _transition_kind(fixture)
        request_id = f"lifecycle:{mode}:{fixture.scenario_id}:{kind}"
        metadata = {
            "suite": "memory_lifecycle_v1",
            "scenario_id": fixture.scenario_id,
            "decision_mode": mode,
            "transition_type": kind,
        }
        if kind == "promotion":
            engine_result = promotion_engine.decide(
                _promotion_context_for_fixture(fixture),
                request_id,
            )
        elif kind == "lifecycle_decision":
            context = lifecycle_context_for_fixture(fixture)
            rule_decision = rule_lifecycle_decision_for_fixture(fixture)
            rule_output = rule_decision.model_dump(mode="json")
            rule_trace = lifecycle_trace_for_rule(
                context=context,
                decision=rule_decision,
                mode="rule",
            )
            llm_result = lifecycle_adapter.decide(
                context,
                request_id=request_id,
                metadata=metadata,
            )
            output, llm_trace, llm_success, failure_reason = lifecycle_engine_result_from_llm(
                result=llm_result,
                mode=LLMDecisionMode(effective_mode),
                rule_output=rule_output,
            )
            engine_result = DecisionEngineResult(
                decision=output if llm_success or effective_mode == "llm" else rule_output,
                rule_trace=rule_trace,
                llm_trace=llm_trace,
                llm_used=True,
                llm_success=llm_success,
                fallback_used=not llm_success,
                errors=[failure_reason] if failure_reason is not None else [],
            )
        else:
            engine_result = belief_engine.update(
                _belief_context_for_fixture(fixture),
                request_id,
            )
        transition_assertion_passed = _transition_assertion_passed(
            fixture=fixture,
            kind=kind,
            decision=engine_result.decision,
        )
        transition_success = transition_assertion_passed and (
            effective_mode != "llm" or engine_result.llm_success is True
        )
        fallback_reason = engine_result.errors[0] if engine_result.errors else None
        lifecycle_rows.append(
            {
                "scenario_id": fixture.scenario_id,
                "transition_type": kind,
                "decision_mode": mode,
                "effective_decision_mode": effective_mode,
                "llm_call_made": engine_result.llm_used,
                "fallback_used": engine_result.fallback_used,
                "fallback_reason": fallback_reason,
                "final_output_source": "rule" if engine_result.fallback_used else "llm",
                "request_id": request_id,
                "success": transition_success,
                "failure_mode": fallback_reason,
                "transition_assertion_passed": transition_assertion_passed,
                "lifecycle_assertion_passed": transition_success,
                "output": engine_result.decision,
            }
        )
        if engine_result.llm_trace is not None:
            llm_rows.append(
                {
                    "scenario_id": fixture.scenario_id,
                    "transition_type": kind,
                    "decision_mode": mode,
                    "effective_decision_mode": effective_mode,
                    "trace": engine_result.llm_trace.model_dump(mode="json"),
                    "success": engine_result.llm_success,
                    "fallback_used": engine_result.fallback_used,
                    "failure_mode": fallback_reason,
                    "output": engine_result.decision,
                }
            )
    return lifecycle_rows, llm_rows


class _ExpectedLifecycleFakeAdapter:
    provider_name = "fake"

    def __init__(self, *, fixtures: list[BenchmarkScenarioFixture], registry: PromptRegistry) -> None:
        self._registry = registry
        self._expected_by_scenario = {
            fixture.scenario_id: expected_lifecycle_decision_for_fixture(fixture)
            for fixture in fixtures
            if fixture.lifecycle is not None
            and lifecycle_family_requires_decision(fixture.lifecycle.family)
        }

    def decide(
        self,
        context: object,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        lifecycle_context = LifecycleDecisionContext.model_validate(context)
        contract = self._registry.load("lifecycle_decision:v1")
        request = LLMStructuredRequest(
            request_id=request_id,
            prompt_ref="lifecycle_decision:v1",
            prompt_hash="dry-run",
            system="",
            user="",
            output_schema=contract.output_schema,
            model_defaults=contract.model_defaults,
            metadata=metadata or {},
        )
        decision = self._expected_by_scenario[lifecycle_context.scenario_id]
        return fake_llm_result_for_lifecycle(request=request, decision=decision, provider_name=self.provider_name)


class _ExpectedExecutionGraphFakeAdapter:
    provider_name = "fake"

    def __init__(self, *, scenarios: list[ExecutionGraphScenario], registry: PromptRegistry) -> None:
        self._registry = registry
        self._expected_by_scenario = {
            scenario.scenario_id: expected_execution_graph_decision_for_scenario(scenario)
            for scenario in scenarios
        }

    def decide(
        self,
        context: object,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        graph_context = ExecutionGraphDecisionContext.model_validate(context)
        contract = self._registry.load("execution_graph_decision:v1")
        request = LLMStructuredRequest(
            request_id=request_id,
            prompt_ref="execution_graph_decision:v1",
            prompt_hash="dry-run",
            system="",
            user="",
            output_schema=contract.output_schema,
            model_defaults=contract.model_defaults,
            metadata=metadata or {},
        )
        decision = self._expected_by_scenario[graph_context.scenario_id]
        return fake_llm_result_for_execution_graph(
            request=request,
            decision=decision,
            provider_name=self.provider_name,
        )


class _ExpectedRetrievalRelevanceFakeAdapter:
    provider_name = "fake"

    def __init__(self, *, fixtures: list[BenchmarkScenarioFixture], registry: PromptRegistry) -> None:
        self._registry = registry
        self._expected_by_scenario = {
            fixture.scenario_id: expected_retrieval_relevance_decision_for_fixture(fixture)
            for fixture in normalize_fixtures(fixtures)
            if fixture.retrieval is not None
        }

    def decide(
        self,
        context: object,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        relevance_context = RetrievalRelevanceContext.model_validate(context)
        contract = self._registry.load("retrieval_relevance:v1")
        request = LLMStructuredRequest(
            request_id=request_id,
            prompt_ref="retrieval_relevance:v1",
            prompt_hash="dry-run",
            system="",
            user="",
            output_schema=contract.output_schema,
            model_defaults=contract.model_defaults,
            metadata=metadata or {},
        )
        decision = self._expected_by_scenario[relevance_context.scenario_id]
        return fake_llm_result_for_retrieval_relevance(
            request=request,
            decision=decision,
            provider_name=self.provider_name,
        )


def _run_retrieval_relevance_decisions(
    *,
    fixtures: list[BenchmarkScenarioFixture],
    mode: str,
    dry_run: bool,
    allow_live: bool,
    prompt_root: Path,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    env_snapshot = load_memorii_environment()
    runtime_config = LLMRuntimeConfig.from_env(env_snapshot.env)
    decision_config = (
        LLMDecisionRuntimeConfig(mode=mode)
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
    if effective_mode in {"llm", "hybrid"}:
        client = EvalFakeClient() if dry_run else LLMClientFactory.from_config(runtime_config)
        runner = PromptLLMRunner(client=client, config=runtime_config)
        adapter = (
            _ExpectedRetrievalRelevanceFakeAdapter(fixtures=fixtures, registry=registry)
            if dry_run and EvalFakeClient is _DEFAULT_EVAL_FAKE_CLIENT
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
            llm_result = adapter.decide(
                context,
                request_id=request_id,
                metadata={
                    "suite": "retrieval_corruption_v1",
                    "scenario_id": fixture.scenario_id,
                    "decision_mode": mode,
                    "transition_type": "retrieval_relevance",
                },
            )
            output, llm_trace, llm_success, fallback_reason = retrieval_relevance_engine_result_from_llm(
                result=llm_result,
                mode=LLMDecisionMode(effective_mode),
                rule_output=rule_output,
            )
            final_output_source = "llm" if llm_success else "rule"
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


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _print_summary(*, suite: str, systems: str, mode: str, report: BenchmarkRunReport, run_dir: Path, llm_call_count: int) -> None:
    memorii_results = [result for result in report.scenario_results if result.system == BenchmarkSystem.MEMORII]
    scenario_count = len({result.scenario_id for result in report.scenario_results})
    passed = sum(1 for result in memorii_results if result.observation.scenario_success is True)
    failed = sum(1 for result in memorii_results if result.observation.scenario_success is False)
    baseline_results = [result for result in report.scenario_results if result.system != BenchmarkSystem.MEMORII]
    baseline_passed = sum(1 for result in baseline_results if result.observation.scenario_success is True)
    baseline_failed = sum(1 for result in baseline_results if result.observation.scenario_success is False)
    lifecycle_results = [
        result for result in memorii_results if result.observation.lifecycle_success is not None
    ]
    lifecycle_passed = sum(1 for result in lifecycle_results if result.observation.lifecycle_success is True)
    lifecycle_failed = sum(1 for result in lifecycle_results if result.observation.lifecycle_success is False)
    baseline_summary = (
        f"baseline_runs={len(baseline_results)} "
        f"baseline_runs_passed={baseline_passed} baseline_runs_failed={baseline_failed} "
        if baseline_results
        else ""
    )

    print(
        f"suite={suite} mode={mode} systems={systems} "
        f"scenarios={scenario_count} "
        f"memorii_runs={len(memorii_results)} "
        f"memorii_runs_passed={passed} memorii_runs_failed={failed} "
        f"{baseline_summary}"
        f"lifecycle_cases={len(lifecycle_results)} "
        f"lifecycle_passed={lifecycle_passed} lifecycle_failed={lifecycle_failed} "
        f"llm_calls={llm_call_count} "
        f"artifacts={run_dir}"
    )


def _run_execution_graph_transitions(
    *,
    scenarios: list[ExecutionGraphScenario],
    mode: str,
    dry_run: bool,
    allow_live: bool,
    prompt_root: Path,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    env_snapshot = load_memorii_environment()
    runtime_config = LLMRuntimeConfig.from_env(env_snapshot.env)
    decision_config = (
        LLMDecisionRuntimeConfig(mode=mode)
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
    if effective_mode in {"llm", "hybrid"}:
        client = EvalFakeClient() if dry_run else LLMClientFactory.from_config(runtime_config)
        runner = PromptLLMRunner(client=client, config=runtime_config)
        adapter = (
            _ExpectedExecutionGraphFakeAdapter(scenarios=scenarios, registry=registry)
            if dry_run and EvalFakeClient is _DEFAULT_EVAL_FAKE_CLIENT
            else LLMExecutionGraphDecisionAdapter(runner=runner, registry=registry)
        )

    rows: list[dict[str, object]] = []
    llm_rows: list[dict[str, object]] = []
    for scenario in scenarios:
        context = execution_graph_context_for_scenario(scenario)
        rule_decision = rule_execution_graph_decision_for_scenario(scenario)
        rule_output = rule_decision.model_dump(mode="json")
        rule_trace = execution_graph_trace_for_rule(
            context=context,
            decision=rule_decision,
            mode="rule",
        )
        request_id = f"execution_graph:{mode}:{scenario.scenario_id}:execution_graph_decision"
        output = rule_output
        llm_success = False
        llm_used = False
        fallback_used = effective_mode in {"auto", "hybrid"} and effective_mode == "rule"
        fallback_reason = "llm_not_configured" if fallback_used else None
        final_output_source = "rule"

        if effective_mode in {"llm", "hybrid"} and adapter is not None:
            llm_used = True
            llm_result = adapter.decide(
                context,
                request_id=request_id,
                metadata={
                    "suite": "execution_graph_v1",
                    "scenario_id": scenario.scenario_id,
                    "decision_mode": mode,
                    "transition_type": "execution_graph_decision",
                },
            )
            output, llm_trace, llm_success, fallback_reason = execution_graph_engine_result_from_llm(
                result=llm_result,
                mode=LLMDecisionMode(effective_mode),
                rule_output=rule_output,
            )
            if effective_mode == "llm" and not llm_success:
                final_output_source = "llm"
            else:
                final_output_source = "rule" if not llm_success else "llm"
            llm_rows.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "transition_type": "execution_graph_decision",
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

        assertion_passed = execution_graph_assertion_passed(scenario=scenario, decision=output)
        success = assertion_passed and (effective_mode != "llm" or llm_success or not llm_used)
        rows.append(
            {
                "scenario_id": scenario.scenario_id,
                "family": scenario.family,
                "decision_mode": mode,
                "effective_decision_mode": effective_mode,
                "llm_call_made": llm_used,
                "fallback_used": (effective_mode in {"auto", "hybrid"} and not llm_success)
                if llm_used
                else fallback_used,
                "fallback_reason": fallback_reason,
                "final_output_source": final_output_source,
                "request_id": request_id if llm_used else rule_trace.trace_id,
                "success": success,
                "failure_mode": None if success else (fallback_reason or "execution_graph_assertion_failed"),
                "transition_assertion_passed": assertion_passed,
                "execution_graph_assertion_passed": assertion_passed,
                "output": output,
            }
        )
    return rows, llm_rows


def _write_execution_graph_artifacts(
    *,
    scenarios: list[ExecutionGraphScenario],
    rows: list[dict[str, object]],
    llm_rows: list[dict[str, object]],
    suite: str,
    mode: str,
    storage_root: str,
    fixture_source: str,
) -> Path:
    run_id = build_run_id(
        config=BenchmarkRunConfig(seed=7, run_label=f"{suite}_{mode}"),
        fixtures=[],
    )
    run_dir = Path(storage_root) / "benchmark_runs" / suite / mode / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    passed = sum(1 for row in rows if row["success"] is True)
    failed = len(rows) - passed
    report = {
        "suite": suite,
        "mode": mode,
        "generated_at": datetime.now(UTC).isoformat(),
        "fixture_source": fixture_source,
        "total_cases": len(rows),
        "passed": passed,
        "failed": failed,
        "llm_calls": len(llm_rows),
        "scenario_results": rows,
    }
    (run_dir / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (run_dir / "report.md").write_text(
        f"# {suite}\n\nmode={mode} total={len(rows)} passed={passed} failed={failed} llm_calls={len(llm_rows)}\n",
        encoding="utf-8",
    )
    (run_dir / "fixtures.json").write_text(
        json.dumps([scenario.model_dump(mode="json") for scenario in scenarios], indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (run_dir / "baseline.json").write_text(
        json.dumps({"suite": suite, "mode": mode, "baseline": "memorii"}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_jsonl(run_dir / "execution_graph_traces.jsonl", rows)
    _write_jsonl(run_dir / "llm_traces.jsonl", llm_rows)
    _write_jsonl(run_dir / "failures.jsonl", [row for row in rows if row["success"] is False])
    return run_dir


def _print_execution_graph_summary(
    *,
    suite: str,
    mode: str,
    run_dir: Path,
    rows: list[dict[str, object]],
    llm_rows: list[dict[str, object]],
) -> None:
    passed = sum(1 for row in rows if row["success"] is True)
    failed = len(rows) - passed
    print(
        f"suite={suite} mode={mode} systems=memorii "
        f"execution_cases={len(rows)} passed={passed} failed={failed} "
        f"llm_calls={len(llm_rows)} artifacts={run_dir}"
    )


def _run_execution_graph_suite(args: argparse.Namespace, *, prompt_root: Path) -> int:
    scenarios, fixture_source = _load_execution_graph_suite(args.suite)
    modes = ["rule", "llm", "hybrid"] if args.mode == "all" else [args.mode]
    for mode in modes:
        rows, llm_rows = _run_execution_graph_transitions(
            scenarios=scenarios,
            mode=mode,
            dry_run=args.dry_run,
            allow_live=args.allow_live,
            prompt_root=prompt_root,
        )
        run_dir = _write_execution_graph_artifacts(
            scenarios=scenarios,
            rows=rows,
            llm_rows=llm_rows,
            suite=args.suite,
            mode=mode,
            storage_root=args.storage_root,
            fixture_source=fixture_source,
        )
        _print_execution_graph_summary(
            suite=args.suite,
            mode=mode,
            run_dir=run_dir,
            rows=rows,
            llm_rows=llm_rows,
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=["memory_lifecycle_v1", "execution_graph_v1", "retrieval_corruption_v1", "minimal"], default="memory_lifecycle_v1")
    parser.add_argument("--mode", choices=["auto", "rule", "llm", "hybrid", "all"], default="auto")
    parser.add_argument("--systems", choices=["memorii", "all"], default="memorii")
    parser.add_argument("--storage-root", default=".memorii")
    parser.add_argument("--prompt-root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-live", action="store_true")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--run-label", default=None)
    args = parser.parse_args(argv)

    prompt_root = Path(args.prompt_root) if args.prompt_root else Path(__file__).resolve().parents[2] / "prompts"
    if args.suite == "execution_graph_v1":
        if args.systems == "all":
            raise SystemExit("execution_graph_v1 currently supports --systems memorii only")
        return _run_execution_graph_suite(args, prompt_root=prompt_root)

    fixtures, fixture_source = _load_suite(args.suite)
    if args.suite == "memory_lifecycle_v1" and args.systems == "all":
        raise SystemExit("memory_lifecycle_v1 currently supports --systems memorii only")

    modes = ["rule", "llm", "hybrid"] if args.mode == "all" else [args.mode]
    for mode in modes:
        run_label = args.run_label or f"{args.suite}_{mode}"
        config = BenchmarkRunConfig(seed=args.seed, run_label=run_label)

        if args.systems == "all":
            report = BenchmarkHarness().run(fixtures=fixtures, config=config)
        else:
            report = _run_memorii_only(fixtures=fixtures, config=config)

        lifecycle_rows: list[dict[str, object]] = []
        retrieval_rows: list[dict[str, object]] = []
        llm_rows: list[dict[str, object]] = []
        if args.suite == "memory_lifecycle_v1":
            lifecycle_rows, llm_rows = _run_lifecycle_transitions(
                fixtures=fixtures,
                mode=mode,
                dry_run=args.dry_run,
                allow_live=args.allow_live,
                prompt_root=prompt_root,
            )
            report = _apply_transition_assertions(report=report, transition_rows=lifecycle_rows)
        if args.suite == "retrieval_corruption_v1":
            retrieval_rows, llm_rows = _run_retrieval_relevance_decisions(
                fixtures=fixtures,
                mode=mode,
                dry_run=args.dry_run,
                allow_live=args.allow_live,
                prompt_root=prompt_root,
            )
            report = _apply_retrieval_relevance_assertions(report=report, retrieval_rows=retrieval_rows)

        root_dir = Path(args.storage_root) / "benchmark_runs" / args.suite / mode
        run_dir = write_artifacts(
            report,
            fixtures=normalize_fixtures(fixtures),
            dataset=args.suite,
            fixture_source=fixture_source,
            subset_size=len(fixtures),
            root_dir=str(root_dir),
        )
        if lifecycle_rows:
            _write_jsonl(run_dir / "lifecycle_traces.jsonl", lifecycle_rows)
        if retrieval_rows:
            _write_jsonl(run_dir / "retrieval_relevance_traces.jsonl", retrieval_rows)
        _write_jsonl(run_dir / "llm_traces.jsonl", llm_rows)
        failures = [
            row for row in [*lifecycle_rows, *retrieval_rows]
            if row.get("success") is False
        ]
        _write_jsonl(run_dir / "failures.jsonl", failures)
        _print_summary(
            suite=args.suite,
            systems=args.systems,
            mode=mode,
            report=report,
            run_dir=run_dir,
            llm_call_count=len(llm_rows),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
