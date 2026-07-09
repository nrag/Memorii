from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from memorii.core.belief.models import BeliefUpdateContext
from memorii.core.belief.rule_provider import RuleBasedBeliefUpdateProvider
from memorii.core.calibration.reports import build_calibration_artifacts
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
from memorii.core.benchmark.memory_evolution_decision import (
    MemoryEvolutionDecisionContext,
    MemoryEvolutionScenario,
    expected_memory_evolution_decision_for_checkpoint,
    fake_llm_result_for_memory_evolution,
    memory_evolution_assertion_passed,
    memory_evolution_context_for_checkpoint,
    memory_evolution_engine_result_from_llm,
    memory_evolution_trace_for_rule,
    rule_memory_evolution_decision_for_checkpoint,
)
from memorii.core.benchmark.memory_evolution_sim import (
    JudgeAggregate,
    LatentGraphScenario,
    MemoryEvolutionSimReconstructionContext,
    SimSystemOutput,
    expected_sim_output_for_checkpoint,
    fake_llm_result_for_memory_evolution_sim,
    generate_memory_evolution_sim_scenarios,
    judge_sim_checkpoint,
    memory_evolution_sim_engine_result_from_llm,
    memory_evolution_sim_trace_for_rule,
    normalize_sim_system_output_for_checkpoint,
    rule_sim_output_for_checkpoint,
    sim_checkpoint_diagnostics,
    sim_metrics_from_rows,
    sim_reconstruction_context_for_checkpoint,
)
from memorii.core.benchmark.memory_evolution_runtime import (
    run_runtime_scenarios,
    runtime_summary_metrics,
    runtime_warning_policy,
    write_runtime_artifacts,
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
from memorii.core.benchmark.hotpotqa import build_hotpotqa_benchmark_fixtures
from memorii.core.benchmark.hotpotqa import load_hotpotqa_examples, select_hotpotqa_subset
from memorii.core.benchmark.hotpotqa_official import (
    HotpotQAPrediction,
    build_hotpotqa_error_analysis,
    build_hotpotqa_stage_diagnostics,
    evaluate_hotpotqa_predictions,
    expected_hotpotqa_grounding_decisions,
    hotpotqa_answer_format_diagnostic,
    hotpotqa_evidence_context_for_example,
    hotpotqa_supporting_fact_candidate_ids,
    hotpotqa_supporting_fact_pairs_from_candidate_ids,
    score_hotpotqa_example,
)
from memorii.core.grounding.models import (
    AnswerVerificationContext,
    EvidenceSelectionContext,
    EvidenceSelectionDecision,
    GroundedAnswerContext,
)
from memorii.core.grounding.pipeline import (
    GroundedAnswerPipeline,
    fake_llm_result_for_answer_verification,
    fake_llm_result_for_evidence_selection,
    fake_llm_result_for_grounded_answer,
)
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
    LLMAnswerVerificationAdapter,
    LLMBeliefUpdateAdapter,
    LLMEvidenceSelectionAdapter,
    LLMGroundedAnswerAdapter,
    LLMLifecycleDecisionAdapter,
    LLMMemoryEvolutionDecisionAdapter,
    LLMMemoryEvolutionSimReconstructionAdapter,
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
from tests.fixtures.benchmarks.memory_evolution_v1 import load_memory_evolution_v1_fixture_set
from tests.fixtures.benchmarks.memory_lifecycle_v1 import load_memory_lifecycle_v1_fixture_set
from tests.fixtures.benchmarks.retrieval_corruption_v1 import load_retrieval_corruption_v1_fixture_set

_DEFAULT_EVAL_FAKE_CLIENT = EvalFakeClient
_DEFAULT_HOTPOTQA_DATASET = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "benchmarks" / "hotpotqa_sample.json"


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


def _load_memory_evolution_suite(suite: str) -> tuple[list[MemoryEvolutionScenario], str]:
    if suite == "memory_evolution_v1":
        return (
            load_memory_evolution_v1_fixture_set(),
            "tests/fixtures/benchmarks/memory_evolution_v1.py",
        )
    raise ValueError(f"Unsupported memory evolution benchmark suite: {suite}")


def _load_memory_evolution_sim_suite(args: argparse.Namespace) -> tuple[list[LatentGraphScenario], str]:
    if args.sim_fixture_path:
        payload = json.loads(Path(args.sim_fixture_path).read_text(encoding="utf-8"))
        return (
            [LatentGraphScenario.model_validate(item) for item in payload],
            str(args.sim_fixture_path),
        )
    return (
        generate_memory_evolution_sim_scenarios(
            profile=args.sim_profile,
            scenario_count=args.sim_scenario_count,
            seed=args.seed,
            min_events=args.sim_min_events,
            max_events=args.sim_max_events,
            noise_rate=args.sim_noise_rate,
        ),
        f"generated:{args.sim_profile}:seed={args.seed}",
    )


def _load_hotpotqa_suite(args: argparse.Namespace) -> tuple[list[BenchmarkScenarioFixture], str, dict[str, object]]:
    fixtures, metadata = build_hotpotqa_benchmark_fixtures(
        dataset_path=args.hotpotqa_dataset,
        split=args.hotpotqa_split,
        seed=args.seed,
        subset_size=args.hotpotqa_subset_size,
        question_type=args.hotpotqa_question_type,
    )
    return fixtures, str(args.hotpotqa_dataset), metadata.model_dump(mode="json")


def _load_hotpotqa_official_examples(args: argparse.Namespace):
    examples = load_hotpotqa_examples(args.hotpotqa_dataset, split=args.hotpotqa_split)
    return select_hotpotqa_subset(
        examples,
        dataset_source=str(args.hotpotqa_dataset),
        split=args.hotpotqa_split,
        seed=args.seed,
        subset_size=args.hotpotqa_subset_size,
        question_type=args.hotpotqa_question_type,
    )


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


class _ExpectedMemoryEvolutionFakeAdapter:
    provider_name = "fake"

    def __init__(self, *, scenarios: list[MemoryEvolutionScenario], registry: PromptRegistry) -> None:
        self._registry = registry
        self._expected_by_key = {
            (scenario.scenario_id, checkpoint.checkpoint_id): expected_memory_evolution_decision_for_checkpoint(
                scenario=scenario,
                checkpoint=checkpoint,
            )
            for scenario in scenarios
            for checkpoint in scenario.checkpoints
        }

    def decide(
        self,
        context: object,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        evolution_context = MemoryEvolutionDecisionContext.model_validate(context)
        contract = self._registry.load("memory_evolution_decision:v1")
        request = LLMStructuredRequest(
            request_id=request_id,
            prompt_ref="memory_evolution_decision:v1",
            prompt_hash="dry-run",
            system="",
            user="",
            output_schema=contract.output_schema,
            model_defaults=contract.model_defaults,
            metadata=metadata or {},
        )
        decision = self._expected_by_key[
            (evolution_context.scenario_id, evolution_context.checkpoint.checkpoint_id)
        ]
        return fake_llm_result_for_memory_evolution(
            request=request,
            decision=decision,
            provider_name=self.provider_name,
        )


class _ExpectedMemoryEvolutionSimFakeAdapter:
    provider_name = "fake"

    def __init__(self, *, scenarios: list[LatentGraphScenario], registry: PromptRegistry) -> None:
        self._registry = registry
        self._expected_by_key = {
            (scenario.scenario_id, checkpoint.checkpoint_id): expected_sim_output_for_checkpoint(checkpoint)
            for scenario in scenarios
            for checkpoint in scenario.checkpoints
        }

    def decide(
        self,
        context: MemoryEvolutionSimReconstructionContext,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        contract = self._registry.load("memory_evolution_sim_reconstruction:v1")
        request = LLMStructuredRequest(
            request_id=request_id,
            prompt_ref="memory_evolution_sim_reconstruction:v1",
            prompt_hash="dry-run",
            system="",
            user="",
            output_schema=contract.output_schema,
            model_defaults=contract.model_defaults,
            metadata=metadata or {},
        )
        decision = self._expected_by_key[(context.scenario_id, context.checkpoint.checkpoint_id)]
        return fake_llm_result_for_memory_evolution_sim(
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


class _ExpectedHotpotQAEvidenceSelectionFakeAdapter:
    provider_name = "fake"

    def __init__(self, *, examples: list[object], registry: PromptRegistry) -> None:
        self._registry = registry
        self._expected_by_example = {
            example.example_id: expected_hotpotqa_grounding_decisions(example)[0]
            for example in examples
        }

    def decide(
        self,
        context: object,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        evidence_context = EvidenceSelectionContext.model_validate(context)
        contract = self._registry.load("evidence_selection:v1")
        request = LLMStructuredRequest(
            request_id=request_id,
            prompt_ref="evidence_selection:v1",
            prompt_hash="dry-run",
            system="",
            user="",
            output_schema=contract.output_schema,
            model_defaults=contract.model_defaults,
            metadata=metadata or {},
        )
        decision = self._expected_by_example[str(evidence_context.metadata["example_id"])]
        return fake_llm_result_for_evidence_selection(
            request=request,
            decision=decision,
            provider_name=self.provider_name,
        )


class _ExpectedHotpotQAGroundedAnswerFakeAdapter:
    provider_name = "fake"

    def __init__(self, *, examples: list[object], registry: PromptRegistry) -> None:
        self._registry = registry
        self._expected_by_example = {
            example.example_id: expected_hotpotqa_grounding_decisions(example)[1]
            for example in examples
        }

    def decide(
        self,
        context: object,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        answer_context = GroundedAnswerContext.model_validate(context)
        contract = self._registry.load("grounded_answer:v1")
        request = LLMStructuredRequest(
            request_id=request_id,
            prompt_ref="grounded_answer:v1",
            prompt_hash="dry-run",
            system="",
            user="",
            output_schema=contract.output_schema,
            model_defaults=contract.model_defaults,
            metadata=metadata or {},
        )
        decision = self._expected_by_example[str(answer_context.metadata["example_id"])]
        return fake_llm_result_for_grounded_answer(
            request=request,
            decision=decision,
            provider_name=self.provider_name,
        )


class _ExpectedHotpotQAAnswerVerificationFakeAdapter:
    provider_name = "fake"

    def __init__(self, *, examples: list[object], registry: PromptRegistry) -> None:
        self._registry = registry
        self._expected_by_example = {
            example.example_id: expected_hotpotqa_grounding_decisions(example)[2]
            for example in examples
        }

    def decide(
        self,
        context: object,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        verification_context = AnswerVerificationContext.model_validate(context)
        contract = self._registry.load("answer_verification:v1")
        request = LLMStructuredRequest(
            request_id=request_id,
            prompt_ref="answer_verification:v1",
            prompt_hash="dry-run",
            system="",
            user="",
            output_schema=contract.output_schema,
            model_defaults=contract.model_defaults,
            metadata=metadata or {},
        )
        decision = self._expected_by_example[str(verification_context.metadata["example_id"])]
        return fake_llm_result_for_answer_verification(
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


def _run_memory_evolution_transitions(
    *,
    scenarios: list[MemoryEvolutionScenario],
    mode: str,
    dry_run: bool,
    allow_live: bool,
    prompt_root: Path,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
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
            _ExpectedMemoryEvolutionFakeAdapter(scenarios=scenarios, registry=registry)
            if dry_run and EvalFakeClient is _DEFAULT_EVAL_FAKE_CLIENT
            else LLMMemoryEvolutionDecisionAdapter(runner=runner, registry=registry)
        )

    scenario_rows: list[dict[str, object]] = []
    checkpoint_rows: list[dict[str, object]] = []
    llm_rows: list[dict[str, object]] = []
    for scenario in scenarios:
        scenario_checkpoint_rows: list[dict[str, object]] = []
        for checkpoint in scenario.checkpoints:
            context = memory_evolution_context_for_checkpoint(
                scenario=scenario,
                checkpoint=checkpoint,
            )
            rule_decision = rule_memory_evolution_decision_for_checkpoint(
                scenario=scenario,
                checkpoint=checkpoint,
            )
            rule_output = rule_decision.model_dump(mode="json")
            rule_trace = memory_evolution_trace_for_rule(
                context=context,
                decision=rule_decision,
                mode="rule",
            )
            request_id = f"memory_evolution:{mode}:{scenario.scenario_id}:{checkpoint.checkpoint_id}"
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
                        "suite": "memory_evolution_v1",
                        "scenario_id": scenario.scenario_id,
                        "checkpoint_id": checkpoint.checkpoint_id,
                        "decision_mode": mode,
                        "transition_type": "memory_evolution_decision",
                    },
                )
                output, llm_trace, llm_success, fallback_reason = memory_evolution_engine_result_from_llm(
                    result=llm_result,
                    mode=LLMDecisionMode(effective_mode),
                    rule_output=rule_output,
                )
                if effective_mode == "llm" and not llm_success:
                    final_output_source = "llm"
                else:
                    final_output_source = "llm" if llm_success else "rule"
                llm_rows.append(
                    {
                        "scenario_id": scenario.scenario_id,
                        "checkpoint_id": checkpoint.checkpoint_id,
                        "transition_type": "memory_evolution_decision",
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

            assertion_passed = memory_evolution_assertion_passed(
                scenario=scenario,
                checkpoint=checkpoint,
                decision=output,
            )
            success = assertion_passed and (effective_mode != "llm" or llm_success or not llm_used)
            checkpoint_row = {
                "scenario_id": scenario.scenario_id,
                "family": scenario.family,
                "checkpoint_id": checkpoint.checkpoint_id,
                "query_or_task": checkpoint.query_or_task,
                "discriminative": scenario.discriminative,
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
                "failure_mode": None if success else (fallback_reason or "memory_evolution_assertion_failed"),
                "transition_assertion_passed": assertion_passed,
                "memory_evolution_assertion_passed": assertion_passed,
                "expected": checkpoint.model_dump(mode="json"),
                "output": output,
            }
            checkpoint_rows.append(checkpoint_row)
            scenario_checkpoint_rows.append(checkpoint_row)

        scenario_success = all(row["success"] is True for row in scenario_checkpoint_rows)
        scenario_rows.append(
            {
                "scenario_id": scenario.scenario_id,
                "family": scenario.family,
                "discriminative": scenario.discriminative,
                "decision_mode": mode,
                "effective_decision_mode": effective_mode,
                "checkpoint_count": len(scenario_checkpoint_rows),
                "success": scenario_success,
                "failure_mode": None if scenario_success else "one_or_more_checkpoints_failed",
                "checkpoints_passed": sum(1 for row in scenario_checkpoint_rows if row["success"] is True),
                "checkpoints_failed": sum(1 for row in scenario_checkpoint_rows if row["success"] is False),
            }
        )
    return scenario_rows, checkpoint_rows, llm_rows


def _write_memory_evolution_artifacts(
    *,
    scenarios: list[MemoryEvolutionScenario],
    scenario_rows: list[dict[str, object]],
    checkpoint_rows: list[dict[str, object]],
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
    passed = sum(1 for row in scenario_rows if row["success"] is True)
    failed = len(scenario_rows) - passed
    report = {
        "suite": suite,
        "mode": mode,
        "generated_at": datetime.now(UTC).isoformat(),
        "fixture_source": fixture_source,
        "scenarios": len(scenario_rows),
        "checkpoints": len(checkpoint_rows),
        "passed": passed,
        "failed": failed,
        "llm_calls": len(llm_rows),
        "scenario_results": scenario_rows,
        "checkpoint_results": checkpoint_rows,
    }
    report_json = json.dumps(report, indent=2, sort_keys=True)
    report_md = (
        f"# {suite}\n\n"
        f"mode={mode} scenarios={len(scenario_rows)} checkpoints={len(checkpoint_rows)} "
        f"passed={passed} failed={failed} llm_calls={len(llm_rows)}\n"
    )
    (run_dir / "report.json").write_text(report_json, encoding="utf-8")
    (run_dir / "memory_evolution_report.json").write_text(report_json, encoding="utf-8")
    (run_dir / "report.md").write_text(report_md, encoding="utf-8")
    (run_dir / "memory_evolution_report.md").write_text(report_md, encoding="utf-8")
    (run_dir / "fixtures.json").write_text(
        json.dumps([scenario.model_dump(mode="json") for scenario in scenarios], indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_jsonl(run_dir / "memory_evolution_traces.jsonl", scenario_rows)
    _write_jsonl(run_dir / "memory_evolution_checkpoint_traces.jsonl", checkpoint_rows)
    _write_jsonl(run_dir / "llm_traces.jsonl", llm_rows)
    _write_jsonl(run_dir / "failures.jsonl", [row for row in checkpoint_rows if row["success"] is False])
    return run_dir


def _print_memory_evolution_summary(
    *,
    suite: str,
    mode: str,
    run_dir: Path,
    scenario_rows: list[dict[str, object]],
    checkpoint_rows: list[dict[str, object]],
    llm_rows: list[dict[str, object]],
) -> None:
    passed = sum(1 for row in scenario_rows if row["success"] is True)
    failed = len(scenario_rows) - passed
    print(
        f"suite={suite} mode={mode} systems=memorii "
        f"scenarios={len(scenario_rows)} checkpoints={len(checkpoint_rows)} "
        f"passed={passed} failed={failed} "
        f"llm_calls={len(llm_rows)} artifacts={run_dir}"
    )


def _run_memory_evolution_suite(args: argparse.Namespace, *, prompt_root: Path) -> int:
    scenarios, fixture_source = _load_memory_evolution_suite(args.suite)
    modes = ["rule", "llm", "hybrid"] if args.mode == "all" else [args.mode]
    for mode in modes:
        scenario_rows, checkpoint_rows, llm_rows = _run_memory_evolution_transitions(
            scenarios=scenarios,
            mode=mode,
            dry_run=args.dry_run,
            allow_live=args.allow_live,
            prompt_root=prompt_root,
        )
        run_dir = _write_memory_evolution_artifacts(
            scenarios=scenarios,
            scenario_rows=scenario_rows,
            checkpoint_rows=checkpoint_rows,
            llm_rows=llm_rows,
            suite=args.suite,
            mode=mode,
            storage_root=args.storage_root,
            fixture_source=fixture_source,
        )
        _print_memory_evolution_summary(
            suite=args.suite,
            mode=mode,
            run_dir=run_dir,
            scenario_rows=scenario_rows,
            checkpoint_rows=checkpoint_rows,
            llm_rows=llm_rows,
        )
    return 0


def _run_memory_evolution_sim_transitions(
    *,
    scenarios: list[LatentGraphScenario],
    mode: str,
    dry_run: bool,
    allow_live: bool,
    prompt_root: Path,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
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
            _ExpectedMemoryEvolutionSimFakeAdapter(scenarios=scenarios, registry=registry)
            if dry_run and EvalFakeClient is _DEFAULT_EVAL_FAKE_CLIENT
            else LLMMemoryEvolutionSimReconstructionAdapter(runner=runner, registry=registry)
        )

    scenario_rows: list[dict[str, object]] = []
    checkpoint_rows: list[dict[str, object]] = []
    judge_rows: list[dict[str, object]] = []
    llm_rows: list[dict[str, object]] = []

    for scenario in scenarios:
        scenario_checkpoint_rows: list[dict[str, object]] = []
        for checkpoint in scenario.checkpoints:
            context = sim_reconstruction_context_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
            rule_output = rule_sim_output_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
            rule_output_json = rule_output.model_dump(mode="json")
            rule_trace = memory_evolution_sim_trace_for_rule(context=context, decision=rule_output, mode="rule")
            request_id = f"memory_evolution_sim:{mode}:{scenario.scenario_id}:{checkpoint.checkpoint_id}"
            output_json = rule_output_json
            llm_call_made = False
            llm_success = False
            fallback_used = effective_mode in {"auto", "hybrid"} and effective_mode == "rule"
            fallback_reason = "llm_not_configured" if fallback_used else None
            final_output_source = "rule"
            llm_trace = rule_trace

            if effective_mode in {"llm", "hybrid"} and adapter is not None:
                llm_call_made = True
                result = adapter.decide(
                    context,
                    request_id=request_id,
                    metadata={
                        "suite": "memory_evolution_sim_v1",
                        "scenario_id": scenario.scenario_id,
                        "checkpoint_id": checkpoint.checkpoint_id,
                        "decision_mode": mode,
                        "effective_decision_mode": effective_mode,
                        "transition_type": "memory_evolution_sim_reconstruction",
                    },
                )
                output_json, llm_trace, llm_success, fallback_reason = memory_evolution_sim_engine_result_from_llm(
                    result=result,
                    mode=LLMDecisionMode(effective_mode),
                    scenario=scenario,
                    rule_output=rule_output_json,
                )
                if dry_run and EvalFakeClient is _DEFAULT_EVAL_FAKE_CLIENT and llm_success:
                    final_output_source = "fake_oracle"
                elif llm_success:
                    final_output_source = "live_llm"
                else:
                    final_output_source = "rule"
                fallback_used = not llm_success
                llm_rows.append(
                    {
                        "scenario_id": scenario.scenario_id,
                        "checkpoint_id": checkpoint.checkpoint_id,
                        "transition_type": "memory_evolution_sim_reconstruction",
                        "decision_mode": mode,
                        "effective_decision_mode": effective_mode,
                        "final_output_source": final_output_source,
                        "trace": llm_trace.model_dump(mode="json"),
                        "success": llm_success,
                        "fallback_used": fallback_used,
                        "failure_mode": fallback_reason,
                        "output": output_json,
                    }
                )

            raw_output = SimSystemOutput.model_validate(output_json)
            raw_output_json = raw_output.model_dump(mode="json")
            output, normalization = normalize_sim_system_output_for_checkpoint(
                scenario=scenario,
                checkpoint=checkpoint,
                output=raw_output,
            )
            output_json = output.model_dump(mode="json")
            aggregate = judge_sim_checkpoint(
                scenario=scenario,
                checkpoint=checkpoint,
                output=output,
            )
            diagnostics = sim_checkpoint_diagnostics(
                scenario=scenario,
                checkpoint=checkpoint,
                output=output,
                aggregate=aggregate,
            )
            success = aggregate.verdict.value == "pass" and (effective_mode != "llm" or llm_success or not llm_call_made)
            checkpoint_row = {
                "scenario_id": scenario.scenario_id,
                "family": scenario.family,
                "checkpoint_id": checkpoint.checkpoint_id,
                "checkpoint_type": checkpoint.checkpoint_type,
                "query_or_task": checkpoint.query_or_task,
                "decision_mode": mode,
                "effective_decision_mode": effective_mode,
                "llm_call_made": llm_call_made,
                "fallback_used": fallback_used,
                "fallback_reason": fallback_reason,
                "final_output_source": final_output_source,
                "request_id": request_id if llm_call_made else llm_trace.trace_id,
                "success": success,
                "passed": True if success else False,
                "verdict": aggregate.verdict.value,
                "score": aggregate.score,
                "confidence": aggregate.confidence,
                "review_required": aggregate.review_required,
                "failure_buckets": aggregate.critical_failure_buckets,
                "missing_expected_ids": diagnostics["missing_expected_ids"],
                "extra_selected_ids": diagnostics["extra_selected_ids"],
                "answer_match_type": diagnostics["answer_match_type"],
                "failure_classification": diagnostics["failure_classification"],
                "selected_excluded_ids": diagnostics["selected_excluded_ids"],
                "supporting_excluded_ids": diagnostics["supporting_excluded_ids"],
                "rejected_expected_ids": diagnostics["rejected_expected_ids"],
                "missing_rejected_ids": diagnostics["missing_rejected_ids"],
                "missing_rejected_claim_subject_entity_ids": diagnostics["missing_rejected_claim_subject_entity_ids"],
                "supporting_wrong_entity_claim_ids": diagnostics["supporting_wrong_entity_claim_ids"],
                "auto_closed_selected_entity_ids": normalization.auto_closed_selected_entity_ids,
                "auto_closed_rejected_entity_ids": normalization.auto_closed_rejected_entity_ids,
                "auto_closed_context_entity_ids": normalization.auto_closed_context_entity_ids,
                "auto_closed_context_relation_ids": normalization.auto_closed_context_relation_ids,
                "auto_promoted_selected_claim_ids": normalization.auto_promoted_selected_claim_ids,
                "auto_promoted_supporting_claim_ids": normalization.auto_promoted_supporting_claim_ids,
                "auto_promoted_supporting_citation_event_ids": normalization.auto_promoted_supporting_citation_event_ids,
                "auto_rejected_claim_ids": normalization.auto_rejected_claim_ids,
                "normalization_reason_codes": normalization.normalization_reason_codes,
                "normalization_applied": normalization.normalization_applied,
                "selected_noncurrent_claim_ids": diagnostics["selected_noncurrent_claim_ids"],
                "required_definition_claim_ids": diagnostics["required_definition_claim_ids"],
                "missing_definition_claim_ids": diagnostics["missing_definition_claim_ids"],
                "missing_definition_support_claim_ids": diagnostics["missing_definition_support_claim_ids"],
                "selected_entity_role_mismatches": diagnostics["selected_entity_role_mismatches"],
                "missing_selected_subject_entity_ids": diagnostics["missing_selected_subject_entity_ids"],
                "selected_object_entity_instead_of_subject_ids": diagnostics[
                    "selected_object_entity_instead_of_subject_ids"
                ],
                "selected_graph_entity_overbreadth": diagnostics["selected_graph_entity_overbreadth"],
                "selected_nonrequired_graph_entity_ids": diagnostics["selected_nonrequired_graph_entity_ids"],
                "selected_context_only_entity_ids": diagnostics["selected_context_only_entity_ids"],
                "selected_rejected_or_context_entity_ids": diagnostics["selected_rejected_or_context_entity_ids"],
                "supporting_noisy_citation_event_ids": diagnostics["supporting_noisy_citation_event_ids"],
                "context_only_noise_event_ids": diagnostics["context_only_noise_event_ids"],
                "role_misclassification": diagnostics["role_misclassification"],
                "precision_failure_classification": diagnostics["precision_failure_classification"],
                "required_judge_ids": diagnostics["required_judge_ids"],
                "expected": checkpoint.model_dump(mode="json"),
                "candidate_cards": context.model_dump(mode="json"),
                "raw_output": raw_output_json,
                "normalized_output": output_json,
                "output": output_json,
                "judge_aggregate": aggregate.model_dump(mode="json"),
            }
            checkpoint_rows.append(checkpoint_row)
            scenario_checkpoint_rows.append(checkpoint_row)
            judge_rows.append(aggregate.model_dump(mode="json"))

        scenario_success = all(row["success"] is True for row in scenario_checkpoint_rows)
        scenario_rows.append(
            {
                "scenario_id": scenario.scenario_id,
                "family": scenario.family,
                "profile": scenario.profile,
                "decision_mode": mode,
                "effective_decision_mode": effective_mode,
                "checkpoint_count": len(scenario_checkpoint_rows),
                "success": scenario_success,
                "failure_mode": None if scenario_success else "one_or_more_checkpoints_failed",
                "checkpoints_passed": sum(1 for row in scenario_checkpoint_rows if row["success"] is True),
                "checkpoints_failed": sum(1 for row in scenario_checkpoint_rows if row["success"] is False),
            }
        )
    return scenario_rows, checkpoint_rows, judge_rows, llm_rows


def _write_memory_evolution_sim_artifacts(
    *,
    scenarios: list[LatentGraphScenario],
    scenario_rows: list[dict[str, object]],
    checkpoint_rows: list[dict[str, object]],
    judge_rows: list[dict[str, object]],
    llm_rows: list[dict[str, object]],
    suite: str,
    mode: str,
    storage_root: str,
    fixture_source: str,
    args: argparse.Namespace,
) -> Path:
    benchmark_key = build_run_id(
        config=BenchmarkRunConfig(seed=args.seed, run_label=f"{suite}_{mode}_{args.sim_profile}"),
        fixtures=[],
    )
    run_id = benchmark_key if args.dry_run else f"{benchmark_key}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
    run_dir = Path(storage_root) / "benchmark_runs" / suite / mode / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    passed = sum(1 for row in scenario_rows if row["success"] is True)
    failed = len(scenario_rows) - passed
    failure_bucket_counts = Counter(
        bucket
        for row in checkpoint_rows
        for bucket in row.get("failure_buckets", [])
    )
    warning_bucket_counts = Counter(
        bucket
        for row in judge_rows
        for vote in row.get("votes", [])
        if vote.get("verdict") == "pass"
        for bucket in vote.get("failure_buckets", [])
    )
    graph_answer_optional_missing_count = sum(
        1 for row in checkpoint_rows if row.get("answer_match_type") == "optional_missing"
    )
    extra_context_provenance_count = sum(1 for row in checkpoint_rows if _sim_row_has_extra_context_provenance(row))
    if extra_context_provenance_count:
        warning_bucket_counts["extra_context_provenance"] += extra_context_provenance_count
    supporting_pollution_count = sum(
        1
        for row in checkpoint_rows
        if row.get("supporting_excluded_ids") or row.get("supporting_noisy_citation_event_ids")
    )
    selected_pollution_count = sum(
        1
        for row in checkpoint_rows
        if row.get("selected_excluded_ids")
        or row.get("selected_noncurrent_claim_ids")
        or row.get("selected_entity_role_mismatches")
    )
    warning_examples = _sim_warning_examples(checkpoint_rows)
    review_bucket_counts = Counter(
        bucket
        for row in checkpoint_rows
        if _sim_row_needs_review(row)
        for bucket in [
            *row.get("failure_buckets", []),
            *row.get("precision_failure_classification", []),
        ]
    )
    required_judge_failures = sum(
        1
        for row in judge_rows
        for vote in row.get("votes", [])
        if vote.get("verdict") == "fail" and vote.get("judge_id") in _required_judge_ids_from_row(row)
    )
    judge_coverage = {
        "votes": sum(len(row.get("votes", [])) for row in judge_rows),
        "abstentions": sum(
            1
            for row in judge_rows
            for vote in row.get("votes", [])
            if vote.get("verdict") == "abstain"
        ),
        "failures": sum(
            1
            for row in judge_rows
            for vote in row.get("votes", [])
            if vote.get("verdict") == "fail"
        ),
        "required_judge_failures": required_judge_failures,
        "review_required": sum(1 for row in checkpoint_rows if row.get("review_required")),
    }
    fixture_payload = [scenario.model_dump(mode="json") for scenario in scenarios]
    latent_graph_json = json.dumps(fixture_payload, indent=2, sort_keys=True)
    surface_rows = [observation.model_dump(mode="json") for scenario in scenarios for observation in scenario.observations]
    checkpoint_payload = [checkpoint.model_dump(mode="json") for scenario in scenarios for checkpoint in scenario.checkpoints]
    validation_scenario_catalog = [
        {
            "scenario_id": scenario.scenario_id,
            "family": scenario.family,
            "profile": scenario.profile,
            "observation_count": len(scenario.observations),
            "checkpoint_count": len(scenario.checkpoints),
            "checkpoint_types": sorted({checkpoint.checkpoint_type for checkpoint in scenario.checkpoints}),
            "difficulty_tags": sorted({tag for checkpoint in scenario.checkpoints for tag in checkpoint.difficulty_tags}),
            "hidden_item_count": sum(
                1
                for collection_name in ("entities", "claims", "relations")
                for item in getattr(scenario, collection_name)
                if getattr(item, "observability", None) == "hidden"
            ),
            "observed_claim_count": sum(1 for claim in scenario.claims if getattr(claim, "observability", None) == "observed"),
            "inferable_claim_count": sum(1 for claim in scenario.claims if getattr(claim, "observability", None) == "inferable"),
        }
        for scenario in scenarios
    ]
    candidate_card_payload = [
        sim_reconstruction_context_for_checkpoint(scenario=scenario, checkpoint=checkpoint).model_dump(mode="json")
        for scenario in scenarios
        for checkpoint in scenario.checkpoints
    ]
    surface_jsonl = "\n".join(json.dumps(row, sort_keys=True) for row in surface_rows)
    checkpoint_jsonl = "\n".join(json.dumps(row, sort_keys=True) for row in checkpoint_payload)
    candidate_card_jsonl = "\n".join(json.dumps(row, sort_keys=True) for row in candidate_card_payload)
    final_output_source_counts = Counter(str(row.get("final_output_source", "unknown")) for row in checkpoint_rows)
    llm_successes = sum(1 for row in llm_rows if row.get("success") is True)
    fallbacks = sum(1 for row in checkpoint_rows if row.get("fallback_used") is True)
    hidden_item_count = sum(
        1
        for scenario in scenarios
        for collection_name in ("entities", "claims", "relations")
        for item in getattr(scenario, collection_name)
        if getattr(item, "observability", None) == "hidden"
    )
    hidden_pressure_checkpoint_count = len(checkpoint_rows) if hidden_item_count else 0
    base_metrics = sim_metrics_from_rows(checkpoint_rows)
    base_metrics.update(
        {
            "hidden_item_count": float(hidden_item_count),
            "hidden_pressure_checkpoint_count": float(hidden_pressure_checkpoint_count),
            "hidden_answer_leak_rate": (
                sum(
                    1
                    for row in checkpoint_rows
                    if "hidden_fact_answer_leak" in set(row.get("failure_buckets", []) or [])
                )
                / max(1, len(checkpoint_rows))
            ),
            "graph_answer_optional_missing_count": float(graph_answer_optional_missing_count),
            "extra_context_provenance_count": float(extra_context_provenance_count),
            "extra_context_provenance_rate": extra_context_provenance_count / max(1, len(checkpoint_rows)),
            "supporting_pollution_count": float(supporting_pollution_count),
            "selected_pollution_count": float(selected_pollution_count),
        }
    )
    calibration_events, calibration_report, calibration_slices, decision_cost_report = build_calibration_artifacts(
        suite=suite,
        profile=args.sim_profile,
        checkpoint_rows=checkpoint_rows,
    )
    report = {
        "suite": suite,
        "mode": mode,
        "profile": args.sim_profile,
        "seed": args.seed,
        "benchmark_key": benchmark_key,
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "fixture_source": fixture_source,
        "fixture_hashes": {
            "latent_graphs": hashlib.sha256(latent_graph_json.encode("utf-8")).hexdigest(),
            "surface_observations": hashlib.sha256(surface_jsonl.encode("utf-8")).hexdigest(),
            "oracle_checkpoints": hashlib.sha256(checkpoint_jsonl.encode("utf-8")).hexdigest(),
            "candidate_cards": hashlib.sha256(candidate_card_jsonl.encode("utf-8")).hexdigest(),
        },
        "scenario_count": len(scenario_rows),
        "validation_scenario_catalog": validation_scenario_catalog,
        "event_count": sum(len(scenario.observations) for scenario in scenarios),
        "checkpoint_count": len(checkpoint_rows),
        "passed": passed,
        "failed": failed,
        "llm_calls": len(llm_rows),
        "provider_successes": llm_successes,
        "provider_failures": len(llm_rows) - llm_successes,
        "fallbacks": fallbacks,
        "final_output_source_counts": dict(sorted(final_output_source_counts.items())),
        "metrics": base_metrics,
        "calibration": calibration_report.model_dump(mode="json"),
        "decision_quality": decision_cost_report.model_dump(mode="json"),
        "failure_bucket_counts": dict(sorted(failure_bucket_counts.items())),
        "critical_failure_bucket_counts": dict(sorted(failure_bucket_counts.items())),
        "warning_bucket_counts": dict(sorted(warning_bucket_counts.items())),
        "review_bucket_counts": dict(sorted(review_bucket_counts.items())),
        "judge_metrics": judge_coverage,
        "baseline_scores": {},
        "artifact_version": 1,
        "scenario_results": scenario_rows,
        "checkpoint_results": checkpoint_rows,
    }
    report_json = json.dumps(report, indent=2, sort_keys=True)
    report_md = (
        f"# {suite}\n\n"
        f"mode={mode} profile={args.sim_profile} scenarios={len(scenario_rows)} "
        f"events={report['event_count']} checkpoints={len(checkpoint_rows)} "
        f"passed={passed} failed={failed} llm_calls={len(llm_rows)}\n"
    )
    (run_dir / "report.json").write_text(report_json, encoding="utf-8")
    (run_dir / "report.md").write_text(report_md, encoding="utf-8")
    (run_dir / "fixtures.json").write_text(latent_graph_json, encoding="utf-8")
    (run_dir / "latent_graphs.json").write_text(latent_graph_json, encoding="utf-8")
    _write_jsonl(
        run_dir / "world_transitions.jsonl",
        [transition.model_dump(mode="json") for scenario in scenarios for transition in scenario.transitions],
    )
    _write_jsonl(
        run_dir / "surface_observations.jsonl",
        surface_rows,
    )
    _write_jsonl(
        run_dir / "oracle_checkpoints.jsonl",
        checkpoint_payload,
    )
    _write_jsonl(run_dir / "candidate_cards.jsonl", candidate_card_payload)
    (run_dir / "validation_scenario_catalog.json").write_text(
        json.dumps(validation_scenario_catalog, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_jsonl(run_dir / "sim_checkpoint_results.jsonl", checkpoint_rows)
    _write_jsonl(run_dir / "calibration_events.jsonl", [event.model_dump(mode="json") for event in calibration_events])
    (run_dir / "calibration_report.json").write_text(
        json.dumps(calibration_report.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (run_dir / "slice_calibration_report.json").write_text(
        json.dumps(calibration_slices, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (run_dir / "decision_quality_report.json").write_text(
        json.dumps(decision_cost_report.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_jsonl(run_dir / "judge_votes.jsonl", [vote for row in judge_rows for vote in row.get("votes", [])])
    (run_dir / "judge_aggregate.json").write_text(
        json.dumps(judge_rows, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_jsonl(
        run_dir / "judge_conflicts.jsonl",
        [row for row in judge_rows if _judge_row_has_conflict(row)],
    )
    (run_dir / "judge_coverage.json").write_text(
        json.dumps(judge_coverage, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (run_dir / "sim_failure_buckets.json").write_text(
        json.dumps(dict(sorted(failure_bucket_counts.items())), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_jsonl(run_dir / "llm_traces.jsonl", llm_rows)
    _write_jsonl(run_dir / "failures.jsonl", [row for row in checkpoint_rows if row["success"] is False])
    _write_jsonl(run_dir / "sim_warning_examples.jsonl", warning_examples)
    _write_jsonl(run_dir / "review_candidates.jsonl", [row for row in checkpoint_rows if _sim_row_needs_review(row)])
    if args.sim_freeze_output:
        (run_dir / "frozen_fixture.json").write_text(
            json.dumps([scenario.model_dump(mode="json") for scenario in scenarios], indent=2, sort_keys=True),
            encoding="utf-8",
        )
    if args.sim_export_review_set:
        _write_jsonl(Path(args.sim_export_review_set), [row for row in checkpoint_rows if _sim_row_needs_review(row)])
    return run_dir


def _required_judge_ids_from_row(row: dict[str, object]) -> set[str]:
    required = row.get("required_judge_ids", [])
    if isinstance(required, list):
        return {str(judge_id) for judge_id in required}
    return set()


def _judge_row_has_conflict(row: dict[str, object]) -> bool:
    votes = row.get("votes", [])
    if not isinstance(votes, list):
        return False
    concrete = {vote.get("verdict") for vote in votes if vote.get("verdict") != "abstain"}
    return "pass" in concrete and "fail" in concrete


def _sim_row_has_extra_context_provenance(row: dict[str, object]) -> bool:
    output = row.get("output")
    if not isinstance(output, dict):
        return False
    return bool(
        output.get("context_claim_ids")
        or output.get("context_entity_ids")
        or output.get("context_relation_ids")
        or output.get("context_citation_event_ids")
    )


def _sim_warning_examples(checkpoint_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    examples: list[dict[str, object]] = []
    for row in checkpoint_rows:
        output = row.get("output") if isinstance(row.get("output"), dict) else {}
        if not isinstance(output, dict):
            output = {}
        if row.get("answer_match_type") == "optional_missing":
            examples.append(
                {
                    "scenario_id": row.get("scenario_id"),
                    "checkpoint_id": row.get("checkpoint_id"),
                    "checkpoint_type": row.get("checkpoint_type"),
                    "warning_bucket": "graph_answer_optional_missing",
                    "warning_buckets": ["graph_answer_optional_missing"],
                    "reason": "answer text is optional for this checkpoint; structured graph/action channels are authoritative",
                    "selected_claim_ids": output.get("selected_claim_ids", []),
                    "selected_entity_ids": output.get("selected_entity_ids", []),
                }
            )
        if _sim_row_has_extra_context_provenance(row):
            examples.append(
                {
                    "scenario_id": row.get("scenario_id"),
                    "checkpoint_id": row.get("checkpoint_id"),
                    "checkpoint_type": row.get("checkpoint_type"),
                    "warning_bucket": "extra_context_provenance",
                    "warning_buckets": ["extra_context_provenance"],
                    "reason": "context/audit evidence is broader than selected support but is not selected or supporting truth",
                    "context_claim_ids": output.get("context_claim_ids", []),
                    "context_entity_ids": output.get("context_entity_ids", []),
                    "context_relation_ids": output.get("context_relation_ids", []),
                    "context_citation_event_ids": output.get("context_citation_event_ids", []),
                }
            )
        aggregate = row.get("judge_aggregate")
        votes = aggregate.get("votes", []) if isinstance(aggregate, dict) else []
        if isinstance(votes, list):
            for vote in votes:
                if not isinstance(vote, dict) or vote.get("verdict") != "pass":
                    continue
                for bucket in vote.get("failure_buckets", []) or []:
                    examples.append(
                        {
                            "scenario_id": row.get("scenario_id"),
                            "checkpoint_id": row.get("checkpoint_id"),
                            "checkpoint_type": row.get("checkpoint_type"),
                            "warning_bucket": bucket,
                            "warning_buckets": [bucket],
                            "reason": vote.get("rationale", "warning emitted by passing judge"),
                            "failed_ids": vote.get("failed_ids", []),
                            "covered_ids": vote.get("covered_ids", []),
                        }
                    )
    return examples


def _sim_row_needs_review(row: dict[str, object]) -> bool:
    if row.get("success") is False or row.get("review_required") is True:
        return True
    if row.get("role_misclassification") is True:
        return True
    if row.get("selected_excluded_ids") or row.get("supporting_excluded_ids"):
        return True
    if row.get("supporting_noisy_citation_event_ids"):
        return True
    if row.get("precision_failure_classification"):
        return True
    buckets = set(row.get("failure_buckets", []) or [])
    return bool(buckets & {"hidden_fact_hallucinated", "overconfident_wrong_answer", "ambiguous_fact_overcommitted"})


def _print_memory_evolution_sim_summary(
    *,
    suite: str,
    mode: str,
    profile: str,
    run_dir: Path,
    scenarios: list[LatentGraphScenario],
    scenario_rows: list[dict[str, object]],
    checkpoint_rows: list[dict[str, object]],
    llm_rows: list[dict[str, object]],
) -> None:
    passed = sum(1 for row in scenario_rows if row["success"] is True)
    failed = len(scenario_rows) - passed
    event_count = sum(len(scenario.observations) for scenario in scenarios)
    print(
        f"suite={suite} mode={mode} systems=memorii profile={profile} "
        f"scenarios={len(scenario_rows)} events={event_count} checkpoints={len(checkpoint_rows)} "
        f"passed={passed} failed={failed} "
        f"llm_calls={len(llm_rows)} artifacts={run_dir}"
    )


def _run_memory_evolution_sim_suite(args: argparse.Namespace, *, prompt_root: Path) -> int:
    scenarios, fixture_source = _load_memory_evolution_sim_suite(args)
    modes = ["rule", "llm", "hybrid"] if args.mode == "all" else [args.mode]
    for mode in modes:
        scenario_rows, checkpoint_rows, judge_rows, llm_rows = _run_memory_evolution_sim_transitions(
            scenarios=scenarios,
            mode=mode,
            dry_run=args.dry_run,
            allow_live=args.allow_live,
            prompt_root=prompt_root,
        )
        run_dir = _write_memory_evolution_sim_artifacts(
            scenarios=scenarios,
            scenario_rows=scenario_rows,
            checkpoint_rows=checkpoint_rows,
            judge_rows=judge_rows,
            llm_rows=llm_rows,
            suite=args.suite,
            mode=mode,
            storage_root=args.storage_root,
            fixture_source=fixture_source,
            args=args,
        )
        _print_memory_evolution_sim_summary(
            suite=args.suite,
            mode=mode,
            profile=args.sim_profile,
            run_dir=run_dir,
            scenarios=scenarios,
            scenario_rows=scenario_rows,
            checkpoint_rows=checkpoint_rows,
            llm_rows=llm_rows,
        )
    return 0




def _run_memory_evolution_runtime_suite(args: argparse.Namespace, *, prompt_root: Path) -> int:
    scenarios, fixture_source = _load_memory_evolution_sim_suite(args)
    modes = ["rule", "llm", "hybrid"] if args.mode == "all" else [args.mode]
    for mode in modes:
        runtime_rows = run_runtime_scenarios(
            scenarios=scenarios,
            mode=mode,
            dry_run=args.dry_run,
            allow_live=args.allow_live,
            prompt_root=prompt_root,
        )
        run_dir = _write_memory_evolution_sim_artifacts(
            scenarios=scenarios,
            scenario_rows=runtime_rows.scenario_rows,
            checkpoint_rows=runtime_rows.checkpoint_rows,
            judge_rows=runtime_rows.judge_rows,
            llm_rows=runtime_rows.llm_rows,
            suite=args.suite,
            mode=mode,
            storage_root=args.storage_root,
            fixture_source=fixture_source,
            args=args,
        )
        write_runtime_artifacts(run_dir=run_dir, rows=runtime_rows)
        summary = runtime_summary_metrics(runtime_rows)
        report_path = run_dir / "report.json"
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report.setdefault("runtime", {}).update(summary)
            if isinstance(summary.get("runtime_graph_summary"), dict):
                report["runtime_graph_summary"] = summary["runtime_graph_summary"]
            if isinstance(summary.get("runtime_graph_alignments_summary"), dict):
                report["runtime_graph_alignments_summary"] = summary["runtime_graph_alignments_summary"]
            report["warning_policy"] = runtime_warning_policy()
            scalar_summary = {key: value for key, value in summary.items() if not isinstance(value, dict)}
            report["metrics"] = {**report.get("metrics", {}), **scalar_summary}
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        except OSError:
            pass
        _print_memory_evolution_sim_summary(
            suite=args.suite,
            mode=mode,
            profile=args.sim_profile,
            run_dir=run_dir,
            scenarios=scenarios,
            scenario_rows=runtime_rows.scenario_rows,
            checkpoint_rows=runtime_rows.checkpoint_rows,
            llm_rows=runtime_rows.llm_rows,
        )
    return 0

def _role_eligible_proof_citation_ids(decision: EvidenceSelectionDecision) -> list[str]:
    final_support_roles = {
        "direct_answer",
        "bridge",
        "entity_link",
        "comparison_operand",
        "temporal_scope",
        "constraint_support",
        "disambiguation",
    }
    ids: list[str] = []
    seen: set[str] = set()
    for step in decision.proof_steps:
        for citation in step.citations:
            if not citation.required_for_final_support or citation.role not in final_support_roles:
                continue
            if citation.candidate_id in seen:
                continue
            seen.add(citation.candidate_id)
            ids.append(citation.candidate_id)
    return ids


def _run_hotpotqa_answer_decisions(
    *,
    examples: list[object],
    mode: str,
    dry_run: bool,
    allow_live: bool,
    prompt_root: Path,
    force_gold_evidence: bool = False,
) -> tuple[HotpotQAPrediction, list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
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
    evidence_selector = None
    answer_generator = None
    verifier = None
    if effective_mode in {"llm", "hybrid"}:
        client = EvalFakeClient() if dry_run else LLMClientFactory.from_config(runtime_config)
        runner = PromptLLMRunner(client=client, config=runtime_config)
        if dry_run and EvalFakeClient is _DEFAULT_EVAL_FAKE_CLIENT:
            evidence_selector = _ExpectedHotpotQAEvidenceSelectionFakeAdapter(examples=examples, registry=registry)
            answer_generator = _ExpectedHotpotQAGroundedAnswerFakeAdapter(examples=examples, registry=registry)
            verifier = _ExpectedHotpotQAAnswerVerificationFakeAdapter(examples=examples, registry=registry)
        else:
            evidence_selector = LLMEvidenceSelectionAdapter(runner=runner, registry=registry)
            answer_generator = LLMGroundedAnswerAdapter(runner=runner, registry=registry)
            verifier = LLMAnswerVerificationAdapter(runner=runner, registry=registry)
        if force_gold_evidence:
            evidence_selector = _ExpectedHotpotQAEvidenceSelectionFakeAdapter(examples=examples, registry=registry)

    pipeline = GroundedAnswerPipeline(
        mode=LLMDecisionMode(effective_mode),
        evidence_selector=evidence_selector,
        answer_generator=answer_generator,
        verifier=verifier,
    )

    prediction = HotpotQAPrediction()
    answer_rows: list[dict[str, object]] = []
    retrieval_rows: list[dict[str, object]] = []
    llm_rows: list[dict[str, object]] = []
    for example in examples:
        context = hotpotqa_evidence_context_for_example(example)
        if force_gold_evidence:
            gold_ids = set(hotpotqa_supporting_fact_candidate_ids(example))
            context = context.model_copy(
                update={"candidates": [candidate for candidate in context.candidates if candidate.candidate_id in gold_ids]}
            )
        retrieval_rows.append(
            {
                "example_id": example.example_id,
                "question": example.question,
                "candidate_sentence_count": len(context.candidates),
                "candidate_titles": sorted({candidate.title for candidate in context.candidates}),
            }
        )
        request_id = f"grounded_answer:{mode}:{'gold_evidence:' if force_gold_evidence else ''}{example.example_id}"
        result = pipeline.run(
            context,
            request_id_prefix=request_id,
            metadata={
                "suite": "hotpotqa_official_v1",
                "example_id": example.example_id,
                "decision_mode": mode,
                "diagnostic_force_gold_evidence": force_gold_evidence,
            },
        )
        llm_used = effective_mode in {"llm", "hybrid"}
        if llm_used:
            for trace in result.traces:
                transition_type = trace.decision_point.value
                llm_success = trace.status.value == "succeeded" and not trace.fallback_used
                llm_rows.append(
                    {
                        "example_id": example.example_id,
                        "transition_type": transition_type,
                        "decision_mode": mode,
                        "effective_decision_mode": effective_mode,
                        "trace": trace.model_dump(mode="json"),
                        "success": llm_success,
                        "fallback_used": trace.fallback_used,
                        "failure_mode": ",".join(trace.validation_errors) or None,
                        "output": trace.final_output,
                    }
                )
        raw_answer = result.answer_finalization.raw_answer
        exported_answer = result.answer
        proof_supporting_facts = hotpotqa_supporting_fact_pairs_from_candidate_ids(
            example=example,
            candidate_ids=result.proof_citation_candidate_ids,
        )
        required_proof_supporting_facts = hotpotqa_supporting_fact_pairs_from_candidate_ids(
            example=example,
            candidate_ids=result.required_proof_citation_candidate_ids,
        )
        role_eligible_proof_citation_ids = _role_eligible_proof_citation_ids(result.evidence_selection)
        role_eligible_proof_supporting_facts = hotpotqa_supporting_fact_pairs_from_candidate_ids(
            example=example,
            candidate_ids=role_eligible_proof_citation_ids,
        )
        answer_supporting_facts = hotpotqa_supporting_fact_pairs_from_candidate_ids(
            example=example,
            candidate_ids=result.answer_citation_candidate_ids,
        )
        verified_supporting_facts = hotpotqa_supporting_fact_pairs_from_candidate_ids(
            example=example,
            candidate_ids=result.verified_citation_candidate_ids,
        )
        predicted_supporting_facts = hotpotqa_supporting_fact_pairs_from_candidate_ids(
            example=example,
            candidate_ids=result.citation_candidate_ids,
        )
        score = score_hotpotqa_example(
            prediction_answer=exported_answer,
            prediction_supporting_facts=predicted_supporting_facts,
            example=example,
        )
        prediction.answer[example.example_id] = exported_answer
        prediction.sp[example.example_id] = predicted_supporting_facts
        answer_rows.append(
            {
                "example_id": example.example_id,
                "decision_mode": mode,
                "effective_decision_mode": effective_mode,
                "llm_call_made": llm_used,
                "fallback_used": result.fallback_used,
                "fallback_reason": result.failure_mode if result.fallback_used else None,
                "final_output_source": "rule" if result.fallback_used or effective_mode == "rule" else "llm",
                "request_id": request_id,
                "question": example.question,
                "question_type": example.question_type,
                "success": result.success,
                "failure_mode": None if result.success else (result.failure_mode or "grounded_answer_failed"),
                "expected_answer": example.answer,
                "expected_supporting_facts": list(example.supporting_facts),
                "raw_answer": raw_answer,
                "final_answer": exported_answer,
                "exported_answer": exported_answer,
                "answer_format_diagnostic": hotpotqa_answer_format_diagnostic(
                    raw_answer=exported_answer,
                    gold_answer=example.answer,
                ),
                "proof_supporting_facts": proof_supporting_facts,
                "required_proof_supporting_facts": required_proof_supporting_facts,
                "role_eligible_proof_supporting_facts": role_eligible_proof_supporting_facts,
                "answer_supporting_facts": answer_supporting_facts,
                "verified_supporting_facts": verified_supporting_facts,
                "final_supporting_facts": predicted_supporting_facts,
                "predicted_supporting_facts": predicted_supporting_facts,
                "scores": score.model_dump(mode="json"),
                "selected_candidate_ids": result.selected_candidate_ids,
                "proof_citation_candidate_ids": result.proof_citation_candidate_ids,
                "required_proof_citation_candidate_ids": result.required_proof_citation_candidate_ids,
                "role_eligible_proof_citation_candidate_ids": role_eligible_proof_citation_ids,
                "answer_citation_candidate_ids": result.answer_citation_candidate_ids,
                "verified_citation_candidate_ids": result.verified_citation_candidate_ids,
                "citation_candidate_ids": result.citation_candidate_ids,
                "verified": result.verified,
                "question_constraints": [
                    constraint.model_dump(mode="json")
                    for constraint in result.answer_verification.question_constraints
                ],
                "evidence_selection": result.evidence_selection.model_dump(mode="json"),
                "grounded_answer": result.grounded_answer.model_dump(mode="json"),
                "answer_verification": result.answer_verification.model_dump(mode="json"),
                "provenance_reconciliation": result.provenance_reconciliation.model_dump(mode="json"),
                "answer_finalization": result.answer_finalization.model_dump(mode="json"),
                "output": result.model_dump(mode="json", exclude={"traces"}),
            }
        )
    return prediction, answer_rows, retrieval_rows, llm_rows


def _write_hotpotqa_official_artifacts(
    *,
    examples: list[object],
    prediction: HotpotQAPrediction,
    answer_rows: list[dict[str, object]],
    retrieval_rows: list[dict[str, object]],
    llm_rows: list[dict[str, object]],
    metrics: dict[str, float],
    suite: str,
    mode: str,
    storage_root: str,
    fixture_source: str,
    args: argparse.Namespace,
) -> Path:
    selection_key = "|".join(str(example.example_id) for example in examples)
    run_label = args.run_label or (
        f"{suite}_{mode}:"
        f"{fixture_source}:"
        f"{args.hotpotqa_split}:"
        f"{args.hotpotqa_subset_size}:"
        f"{args.hotpotqa_question_type}:"
        f"{selection_key}"
    )
    benchmark_key = build_run_id(
        config=BenchmarkRunConfig(seed=args.seed, run_label=run_label),
        fixtures=[],
    )
    run_instance_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_id = f"{benchmark_key}-{run_instance_id}"
    run_dir = Path(storage_root) / "benchmark_runs" / suite / mode / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    passed = sum(1 for row in answer_rows if row["success"] is True)
    failed = len(answer_rows) - passed
    llm_successes = sum(1 for row in llm_rows if row.get("success") is True)
    llm_failures = len(llm_rows) - llm_successes
    llm_fallbacks = sum(1 for row in llm_rows if row.get("fallback_used") is True)
    provider_errors = sum(1 for row in llm_rows if row.get("failure_mode") == "provider_error")
    metadata = {
        "benchmark_key": benchmark_key,
        "run_id": run_id,
        "run_instance_id": run_instance_id,
        "dataset_path": fixture_source,
        "split": args.hotpotqa_split,
        "seed": args.seed,
        "subset_size_requested": args.hotpotqa_subset_size,
        "question_type": args.hotpotqa_question_type,
        "selected_example_ids": [example.example_id for example in examples],
        "example_count": len(examples),
        "mode": mode,
        "allow_live": bool(args.allow_live),
        "dry_run": bool(args.dry_run),
        "prompt_hashes": sorted(
            {
                str(((row.get("trace") or {}).get("input_payload") or {}).get("prompt_hash"))
                for row in llm_rows
                if isinstance(row.get("trace"), dict)
                and isinstance((row.get("trace") or {}).get("input_payload"), dict)
                and ((row.get("trace") or {}).get("input_payload") or {}).get("prompt_hash") is not None
            }
        ),
        "models": sorted(
            {
                str(((row.get("trace") or {}).get("input_payload") or {}).get("model"))
                for row in llm_rows
                if isinstance(row.get("trace"), dict)
                and isinstance((row.get("trace") or {}).get("input_payload"), dict)
                and ((row.get("trace") or {}).get("input_payload") or {}).get("model") is not None
            }
        ),
        "providers": sorted(
            {
                str(((row.get("trace") or {}).get("input_payload") or {}).get("provider"))
                for row in llm_rows
                if isinstance(row.get("trace"), dict)
                and isinstance((row.get("trace") or {}).get("input_payload"), dict)
                and ((row.get("trace") or {}).get("input_payload") or {}).get("provider") is not None
            }
        ),
    }
    report = {
        "suite": suite,
        "mode": mode,
        "generated_at": datetime.now(UTC).isoformat(),
        "fixture_source": fixture_source,
        "examples": len(examples),
        "passed": passed,
        "failed": failed,
        "llm_calls": len(llm_rows),
        "llm_successes": llm_successes,
        "llm_failures": llm_failures,
        "llm_fallbacks": llm_fallbacks,
        "provider_errors": provider_errors,
        "official_metrics": metrics,
        "scenario_results": answer_rows,
    }
    error_analysis = build_hotpotqa_error_analysis(examples=examples, answer_rows=answer_rows)
    stage_diagnostics = build_hotpotqa_stage_diagnostics(examples=examples, answer_rows=answer_rows)
    (run_dir / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (run_dir / "report.md").write_text(
        (
            f"# {suite}\n\n"
            f"mode={mode} examples={len(examples)} answer_f1={metrics['f1']:.4f} "
            f"sp_f1={metrics['sp_f1']:.4f} joint_f1={metrics['joint_f1']:.4f} "
            f"llm_calls={len(llm_rows)} llm_successes={llm_successes} "
            f"llm_failures={llm_failures} fallbacks={llm_fallbacks} "
            f"provider_errors={provider_errors}\n"
        ),
        encoding="utf-8",
    )
    (run_dir / "predictions.json").write_text(
        json.dumps(prediction.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (run_dir / "official_metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
    (run_dir / "hotpotqa_error_analysis.json").write_text(
        json.dumps(error_analysis, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (run_dir / "hotpotqa_stage_diagnostics.json").write_text(
        json.dumps(stage_diagnostics, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (run_dir / "hotpotqa_metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    _write_jsonl(run_dir / "hotpotqa_answer_traces.jsonl", answer_rows)
    _write_jsonl(run_dir / "hotpotqa_stage_diagnostics.jsonl", list(stage_diagnostics["rows"]))
    _write_jsonl(run_dir / "hotpotqa_retrieval_traces.jsonl", retrieval_rows)
    _write_jsonl(
        run_dir / "evidence_selection_traces.jsonl",
        [
            {
                "example_id": row["example_id"],
                "transition_type": "evidence_selection",
                "decision_mode": row["decision_mode"],
                "effective_decision_mode": row["effective_decision_mode"],
                "output": row["evidence_selection"],
            }
            for row in answer_rows
        ],
    )
    _write_jsonl(
        run_dir / "grounded_answer_traces.jsonl",
        [
            {
                "example_id": row["example_id"],
                "transition_type": "grounded_answer",
                "decision_mode": row["decision_mode"],
                "effective_decision_mode": row["effective_decision_mode"],
                "output": row["grounded_answer"],
            }
            for row in answer_rows
        ],
    )
    _write_jsonl(
        run_dir / "answer_verification_traces.jsonl",
        [
            {
                "example_id": row["example_id"],
                "transition_type": "answer_verification",
                "decision_mode": row["decision_mode"],
                "effective_decision_mode": row["effective_decision_mode"],
                "output": row["answer_verification"],
            }
            for row in answer_rows
        ],
    )
    _write_jsonl(run_dir / "llm_traces.jsonl", llm_rows)
    _write_jsonl(run_dir / "failures.jsonl", [row for row in answer_rows if row["success"] is False])
    return run_dir


def _write_hotpotqa_oracle_diagnostics(
    *,
    examples: list[object],
    mode: str,
    dry_run: bool,
    allow_live: bool,
    prompt_root: Path,
    run_dir: Path,
    official_answer_rows: list[dict[str, object]],
) -> None:
    gold_evidence_prediction, gold_evidence_rows, _, gold_evidence_llm_rows = _run_hotpotqa_answer_decisions(
        examples=examples,
        mode=mode,
        dry_run=dry_run,
        allow_live=allow_live,
        prompt_root=prompt_root,
        force_gold_evidence=True,
    )
    proof_prediction = HotpotQAPrediction()
    gold_citation_prediction = HotpotQAPrediction()
    evidence_selection_rows: list[dict[str, object]] = []
    for example in examples:
        row = next((item for item in official_answer_rows if item["example_id"] == example.example_id), {})
        answer = str(row.get("exported_answer", ""))
        proof_pairs = row.get("proof_supporting_facts", [])
        proof_prediction.answer[example.example_id] = answer
        proof_prediction.sp[example.example_id] = _pairs_from_jsonable(proof_pairs)
        gold_citation_prediction.answer[example.example_id] = answer
        gold_citation_prediction.sp[example.example_id] = list(example.supporting_facts)
        gold_ids = set(hotpotqa_supporting_fact_candidate_ids(example))
        proof_ids = set(row.get("proof_citation_candidate_ids", [])) if isinstance(row.get("proof_citation_candidate_ids"), list) else set()
        evidence_selection_rows.append(
            {
                "example_id": example.example_id,
                "gold_support_in_proof": gold_ids <= proof_ids,
                "gold_support_partially_in_proof": bool(gold_ids & proof_ids),
                "gold_support_candidate_ids": sorted(gold_ids),
                "proof_citation_candidate_ids": sorted(proof_ids),
            }
        )
    diagnostics = {
        "gold_evidence_to_answer": {
            "metrics": evaluate_hotpotqa_predictions(prediction=gold_evidence_prediction, gold_examples=examples),
            "llm_calls": len(gold_evidence_llm_rows),
        },
        "llm_proof_gold_final_citations": {
            "metrics": evaluate_hotpotqa_predictions(prediction=gold_citation_prediction, gold_examples=examples),
        },
        "llm_proof_to_answer_without_reconciliation_loss": {
            "metrics": evaluate_hotpotqa_predictions(prediction=proof_prediction, gold_examples=examples),
        },
        "llm_evidence_selection_only": {
            "full_gold_support_count": sum(1 for row in evidence_selection_rows if row["gold_support_in_proof"]),
            "partial_gold_support_count": sum(1 for row in evidence_selection_rows if row["gold_support_partially_in_proof"]),
            "examples": len(evidence_selection_rows),
            "rows": evidence_selection_rows,
        },
    }
    (run_dir / "hotpotqa_oracle_diagnostics.json").write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_jsonl(run_dir / "hotpotqa_oracle_gold_evidence_answer_traces.jsonl", gold_evidence_rows)
    _write_jsonl(run_dir / "hotpotqa_oracle_llm_traces.jsonl", gold_evidence_llm_rows)


def _pairs_from_jsonable(value: object) -> list[tuple[str, int]]:
    if not isinstance(value, list):
        return []
    pairs: list[tuple[str, int]] = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        title, index = item
        if isinstance(title, str) and isinstance(index, int):
            pairs.append((title, index))
    return pairs


def _print_hotpotqa_official_summary(
    *,
    suite: str,
    mode: str,
    run_dir: Path,
    examples: list[object],
    metrics: dict[str, float],
    llm_rows: list[dict[str, object]],
) -> None:
    llm_successes = sum(1 for row in llm_rows if row.get("success") is True)
    llm_failures = len(llm_rows) - llm_successes
    llm_fallbacks = sum(1 for row in llm_rows if row.get("fallback_used") is True)
    provider_errors = sum(1 for row in llm_rows if row.get("failure_mode") == "provider_error")
    print(
        f"suite={suite} mode={mode} examples={len(examples)} "
        f"answer_f1={metrics['f1']:.4f} sp_f1={metrics['sp_f1']:.4f} "
        f"joint_f1={metrics['joint_f1']:.4f} llm_calls={len(llm_rows)} "
        f"llm_successes={llm_successes} llm_failures={llm_failures} "
        f"fallbacks={llm_fallbacks} provider_errors={provider_errors} "
        f"artifacts={run_dir}"
    )


def _run_hotpotqa_official_suite(args: argparse.Namespace, *, prompt_root: Path) -> int:
    examples = _load_hotpotqa_official_examples(args)
    modes = ["rule", "llm", "hybrid"] if args.mode == "all" else [args.mode]
    for mode in modes:
        prediction, answer_rows, retrieval_rows, llm_rows = _run_hotpotqa_answer_decisions(
            examples=examples,
            mode=mode,
            dry_run=args.dry_run,
            allow_live=args.allow_live,
            prompt_root=prompt_root,
        )
        metrics = evaluate_hotpotqa_predictions(prediction=prediction, gold_examples=examples)
        run_dir = _write_hotpotqa_official_artifacts(
            examples=examples,
            prediction=prediction,
            answer_rows=answer_rows,
            retrieval_rows=retrieval_rows,
            llm_rows=llm_rows,
            metrics=metrics,
            suite=args.suite,
            mode=mode,
            storage_root=args.storage_root,
            fixture_source=str(args.hotpotqa_dataset),
            args=args,
        )
        if args.hotpotqa_diagnostics == "oracle":
            _write_hotpotqa_oracle_diagnostics(
                examples=examples,
                mode=mode,
                dry_run=args.dry_run,
                allow_live=args.allow_live,
                prompt_root=prompt_root,
                run_dir=run_dir,
                official_answer_rows=answer_rows,
            )
        _print_hotpotqa_official_summary(
            suite=args.suite,
            mode=mode,
            run_dir=run_dir,
            examples=examples,
            metrics=metrics,
            llm_rows=llm_rows,
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--suite",
        choices=[
            "memory_lifecycle_v1",
            "execution_graph_v1",
            "memory_evolution_v1",
            "memory_evolution_sim_v1",
            "memory_evolution_runtime_v1",
            "retrieval_corruption_v1",
            "hotpotqa_v1",
            "hotpotqa_official_v1",
            "minimal",
        ],
        default="memory_lifecycle_v1",
    )
    parser.add_argument("--mode", choices=["auto", "rule", "llm", "hybrid", "all"], default="auto")
    parser.add_argument("--systems", choices=["memorii", "all"], default="memorii")
    parser.add_argument("--storage-root", default=".memorii")
    parser.add_argument("--prompt-root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-live", action="store_true")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--run-label", default=None)
    parser.add_argument("--hotpotqa-dataset", default=str(_DEFAULT_HOTPOTQA_DATASET))
    parser.add_argument("--hotpotqa-split", default="validation")
    parser.add_argument("--hotpotqa-subset-size", type=int, default=3)
    parser.add_argument("--hotpotqa-question-type", choices=["bridge", "comparison"], default=None)
    parser.add_argument("--hotpotqa-diagnostics", choices=["none", "oracle"], default="none")
    parser.add_argument("--sim-profile", choices=["smoke", "adversarial", "long_horizon"], default="smoke")
    parser.add_argument("--sim-scenario-count", type=int, default=10)
    parser.add_argument("--sim-min-events", type=int, default=None)
    parser.add_argument("--sim-max-events", type=int, default=None)
    parser.add_argument("--sim-noise-rate", type=float, default=None)
    parser.add_argument("--sim-fixture-path", default=None)
    parser.add_argument("--sim-freeze-output", action="store_true")
    parser.add_argument("--sim-export-review-set", default=None)
    args = parser.parse_args(argv)

    prompt_root = Path(args.prompt_root) if args.prompt_root else Path(__file__).resolve().parents[2] / "prompts"
    if args.suite == "execution_graph_v1":
        if args.systems == "all":
            raise SystemExit("execution_graph_v1 currently supports --systems memorii only")
        return _run_execution_graph_suite(args, prompt_root=prompt_root)
    if args.suite == "memory_evolution_v1":
        if args.systems == "all":
            raise SystemExit("memory_evolution_v1 currently supports --systems memorii only")
        return _run_memory_evolution_suite(args, prompt_root=prompt_root)
    if args.suite == "memory_evolution_sim_v1":
        if args.systems == "all":
            raise SystemExit("memory_evolution_sim_v1 currently supports --systems memorii only")
        return _run_memory_evolution_sim_suite(args, prompt_root=prompt_root)
    if args.suite == "memory_evolution_runtime_v1":
        if args.systems == "all":
            raise SystemExit("memory_evolution_runtime_v1 currently supports --systems memorii only")
        return _run_memory_evolution_runtime_suite(args, prompt_root=prompt_root)
    if args.suite == "hotpotqa_official_v1":
        if args.systems == "all":
            raise SystemExit("hotpotqa_official_v1 currently supports --systems memorii only")
        return _run_hotpotqa_official_suite(args, prompt_root=prompt_root)

    hotpotqa_metadata: dict[str, object] | None = None
    if args.suite == "hotpotqa_v1":
        if args.mode in {"llm", "hybrid"}:
            raise SystemExit("hotpotqa_v1 currently supports deterministic modes only: auto, rule, or all")
        fixtures, fixture_source, hotpotqa_metadata = _load_hotpotqa_suite(args)
    else:
        fixtures, fixture_source = _load_suite(args.suite)
    if args.suite == "memory_lifecycle_v1" and args.systems == "all":
        raise SystemExit("memory_lifecycle_v1 currently supports --systems memorii only")

    modes = ["rule"] if args.suite == "hotpotqa_v1" and args.mode == "all" else (
        ["rule", "llm", "hybrid"] if args.mode == "all" else [args.mode]
    )
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
        if hotpotqa_metadata is not None:
            (run_dir / "hotpotqa_metadata.json").write_text(
                json.dumps(hotpotqa_metadata, indent=2, sort_keys=True),
                encoding="utf-8",
            )
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
