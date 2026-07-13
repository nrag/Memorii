"""Memory lifecycle benchmark suite runner."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from memorii.core.belief.models import BeliefUpdateContext
from memorii.core.belief.rule_provider import RuleBasedBeliefUpdateProvider
from memorii.core.benchmark.fixtures import normalize_fixtures
from memorii.core.benchmark.lifecycle_decision import (
    lifecycle_assertion_passed,
    lifecycle_context_for_fixture,
    lifecycle_engine_result_from_llm,
    lifecycle_family_requires_decision,
    lifecycle_trace_for_rule,
    rule_lifecycle_decision_for_fixture,
)
from memorii.core.benchmark.metrics import compute_metrics
from memorii.core.benchmark.models import (
    BenchmarkRunReport,
    BenchmarkScenarioFixture,
    MemoryLifecycleFamily,
    ScenarioResult,
)
from memorii.core.env_config import load_memorii_environment
from memorii.core.llm_config import DecisionModeName, LLMDecisionRuntimeConfig, LLMLiveTestConfig, LLMRuntimeConfig
from memorii.core.llm_decision.adapters import (
    LLMBeliefUpdateAdapter,
    LLMLifecycleDecisionAdapter,
    LLMPromotionDecisionAdapter,
)
from memorii.core.llm_decision.models import LLMDecisionMode
from memorii.core.llm_eval.engine_result import DecisionEngineResult
from memorii.core.llm_eval.runner import BeliefUpdateEngine, PromotionDecisionEngine
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.promotion.models import PromotionCandidateType, PromotionContext
from memorii.core.promotion.rule_provider import RuleBasedPromotionDecisionProvider
from memorii.core.prompts.registry import PromptRegistry
from memorii.core.solver.abstention import SolverDecision
from memorii.tools.benchmark_registry import BenchmarkSuiteRunner
from memorii.tools.benchmark_suites.common import ALL_DECISION_MODES
from memorii.tools.benchmark_suites.fake_adapters import _ExpectedLifecycleFakeAdapter
from memorii.tools.benchmark_suites.fixture_harness import (
    FixtureBackedBenchmarkSuiteRunner,
    aggregate_by_category,
    aggregate_by_system,
)
from memorii.tools.benchmark_suites.fixture_loaders import load_memory_lifecycle_fixture_set
from memorii.tools.benchmark_suites.runtime_dependencies import BenchmarkRuntimeDependencies
from memorii.tools.run_live_llm_eval import _validate_live_safety

SUITE_NAME = "memory_lifecycle_v1"


def _decision_mode(mode: str) -> DecisionModeName:
    if mode in {"auto", "rule", "llm", "hybrid"}:
        return cast(DecisionModeName, mode)
    raise ValueError(f"Unsupported memory lifecycle mode: {mode}")


def transition_kind(fixture: BenchmarkScenarioFixture) -> str:
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


def apply_transition_assertions(
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
            "aggregate_by_system": aggregate_by_system(updated_results),
            "aggregate_by_category": aggregate_by_category(updated_results),
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
        kind = transition_kind(fixture)
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


def run_lifecycle_transitions(
    fixtures: list[BenchmarkScenarioFixture],
    mode: str,
    dry_run: bool,
    allow_live: bool,
    prompt_root: Path,
    dependencies: BenchmarkRuntimeDependencies,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    env_snapshot = load_memorii_environment()
    runtime_config = LLMRuntimeConfig.from_env(env_snapshot.env)
    decision_config = LLMDecisionRuntimeConfig(mode=_decision_mode(mode)) if mode != "auto" else LLMDecisionRuntimeConfig.from_env(env_snapshot.env)
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

    client = dependencies.eval_fake_client_cls() if dry_run else dependencies.llm_client_factory.from_config(runtime_config)
    runner = PromptLLMRunner(client=client, config=runtime_config)
    registry = PromptRegistry(prompt_root=prompt_root)
    promotion_adapter = LLMPromotionDecisionAdapter(runner=runner, registry=registry)
    belief_adapter = LLMBeliefUpdateAdapter(runner=runner, registry=registry)
    lifecycle_adapter = (
        _ExpectedLifecycleFakeAdapter(fixtures=fixtures, registry=registry)
        if dry_run and dependencies.is_default_fake_client()
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
        kind = transition_kind(fixture)
        request_id = f"lifecycle:{mode}:{fixture.scenario_id}:{kind}"
        metadata: dict[str, object] = {
            "suite": SUITE_NAME,
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


def build_runner(*, dependencies: BenchmarkRuntimeDependencies) -> BenchmarkSuiteRunner:
    return FixtureBackedBenchmarkSuiteRunner(
        suite_name=SUITE_NAME,
        loader=load_memory_lifecycle_fixture_set,
        supported_modes=ALL_DECISION_MODES,
        dependencies=dependencies,
        trace_runner=run_lifecycle_transitions,
        report_mutator=apply_transition_assertions,
        trace_artifact_name="lifecycle_traces.jsonl",
        supports_all_systems=False,
    )
