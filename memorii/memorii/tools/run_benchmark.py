from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from memorii.core.belief.models import BeliefUpdateContext
from memorii.core.belief.rule_provider import RuleBasedBeliefUpdateProvider
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
from memorii.core.llm_decision.adapters import LLMBeliefUpdateAdapter, LLMPromotionDecisionAdapter
from memorii.core.llm_decision.models import LLMDecisionMode
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
from tests.fixtures.benchmarks.memory_lifecycle_v1 import load_memory_lifecycle_v1_fixture_set


def _load_suite(suite: str) -> tuple[list[BenchmarkScenarioFixture], str]:
    if suite == "memory_lifecycle_v1":
        return (
            load_memory_lifecycle_v1_fixture_set(),
            "tests/fixtures/benchmarks/memory_lifecycle_v1.py",
        )
    if suite == "minimal":
        return (
            load_benchmark_fixture_set(),
            "tests/fixtures/benchmarks/benchmark_minimal.py",
        )
    raise ValueError(f"Unsupported benchmark suite: {suite}")


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
    else:
        candidate_type = PromotionCandidateType.SEMANTIC
        content = f"Lifecycle transition candidate for {fixture.scenario_id}."

    related_memory_ids = []
    if family in {
        MemoryLifecycleFamily.MERGE_NEAR_DUPLICATE_PREFERENCE,
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
    } else 0
    decision = SolverDecision.INSUFFICIENT_EVIDENCE if family in {
        MemoryLifecycleFamily.BLOCK_INFERRED_USER_PREFERENCE,
        MemoryLifecycleFamily.AVOID_WRONG_ENTITY_CARRYOVER,
    } else SolverDecision.SUPPORTED
    return BeliefUpdateContext(
        prior_belief=0.5,
        decision=decision,
        evidence_count=2 if decision == SolverDecision.SUPPORTED else 0,
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
    if family in {
        MemoryLifecycleFamily.CREATE_AND_REUSE_USER_PREFERENCE,
        MemoryLifecycleFamily.BLOCK_INFERRED_USER_PREFERENCE,
        MemoryLifecycleFamily.MERGE_NEAR_DUPLICATE_PREFERENCE,
        MemoryLifecycleFamily.PROMOTE_REPEATED_PROJECT_FACT,
        MemoryLifecycleFamily.PRESERVE_TASK_SCOPED_PREFERENCE,
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
            MemoryLifecycleFamily.PRESERVE_TASK_SCOPED_PREFERENCE,
        }:
            return promote is False
        return True
    belief = decision.get("belief")
    return isinstance(belief, int | float) and 0.0 <= float(belief) <= 1.0


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
        else:
            decision, trace = belief_rule.update(context=_belief_context_for_fixture(fixture))
            output = decision.model_dump(mode="json")
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
                "success": True,
                "failure_mode": None,
                "transition_assertion_passed": _transition_assertion_passed(
                    fixture=fixture,
                    kind=kind,
                    decision=output,
                ),
                "lifecycle_assertion_passed": True,
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


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _print_summary(*, suite: str, systems: str, mode: str, report: BenchmarkRunReport, run_dir: Path, llm_call_count: int) -> None:
    memorii_results = [result for result in report.scenario_results if result.system == BenchmarkSystem.MEMORII]
    passed = sum(1 for result in memorii_results if result.observation.scenario_success is True)
    failed = sum(1 for result in memorii_results if result.observation.scenario_success is False)
    lifecycle_results = [
        result for result in memorii_results if result.observation.lifecycle_success is not None
    ]
    lifecycle_passed = sum(1 for result in lifecycle_results if result.observation.lifecycle_success is True)
    lifecycle_failed = sum(1 for result in lifecycle_results if result.observation.lifecycle_success is False)

    print(
        f"suite={suite} mode={mode} systems={systems} "
        f"memorii_cases={len(memorii_results)} passed={passed} failed={failed} "
        f"lifecycle_cases={len(lifecycle_results)} "
        f"lifecycle_passed={lifecycle_passed} lifecycle_failed={lifecycle_failed} "
        f"llm_calls={llm_call_count} "
        f"artifacts={run_dir}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=["memory_lifecycle_v1", "minimal"], default="memory_lifecycle_v1")
    parser.add_argument("--mode", choices=["auto", "rule", "llm", "hybrid", "all"], default="auto")
    parser.add_argument("--systems", choices=["memorii", "all"], default="memorii")
    parser.add_argument("--storage-root", default=".memorii")
    parser.add_argument("--prompt-root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-live", action="store_true")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--run-label", default=None)
    args = parser.parse_args(argv)

    fixtures, fixture_source = _load_suite(args.suite)
    if args.suite == "memory_lifecycle_v1" and args.systems == "all":
        raise SystemExit("memory_lifecycle_v1 currently supports --systems memorii only")

    prompt_root = Path(args.prompt_root) if args.prompt_root else Path(__file__).resolve().parents[2] / "prompts"
    modes = ["rule", "llm", "hybrid"] if args.mode == "all" else [args.mode]
    for mode in modes:
        run_label = args.run_label or f"{args.suite}_{mode}"
        config = BenchmarkRunConfig(seed=args.seed, run_label=run_label)

        if args.systems == "all":
            report = BenchmarkHarness().run(fixtures=fixtures, config=config)
        else:
            report = _run_memorii_only(fixtures=fixtures, config=config)

        lifecycle_rows: list[dict[str, object]] = []
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
        _write_jsonl(run_dir / "llm_traces.jsonl", llm_rows)
        failures = [
            row for row in lifecycle_rows
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
