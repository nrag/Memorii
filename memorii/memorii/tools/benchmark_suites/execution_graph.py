"""Execution graph benchmark suite runner."""

from __future__ import annotations

import argparse
import json
from datetime import (
    UTC,
    datetime,
)
from pathlib import Path
from typing import cast

from memorii.core.benchmark.execution_graph_decision import (
    ExecutionGraphScenario,
    execution_graph_assertion_passed,
    execution_graph_context_for_scenario,
    execution_graph_engine_result_from_llm,
    execution_graph_trace_for_rule,
    rule_execution_graph_decision_for_scenario,
)
from memorii.core.benchmark.fixture_sets.execution_graph_v1 import load_execution_graph_v1_fixture_set
from memorii.core.benchmark.models import BenchmarkRunConfig
from memorii.core.benchmark.reproducibility import build_run_id
from memorii.core.env_config import load_memorii_environment
from memorii.core.llm_config import (
    DecisionModeName,
    LLMDecisionRuntimeConfig,
    LLMLiveTestConfig,
    LLMRuntimeConfig,
)
from memorii.core.llm_decision.adapters import LLMExecutionGraphDecisionAdapter
from memorii.core.llm_decision.models import LLMDecisionMode
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.prompts.registry import PromptRegistry
from memorii.tools.benchmark_registry import BenchmarkSuiteRunner, FunctionBenchmarkSuiteRunner
from memorii.tools.benchmark_suites.artifact_io import _write_jsonl
from memorii.tools.benchmark_suites.common import ALL_DECISION_MODES, require_memorii_only
from memorii.tools.benchmark_suites.fake_adapters import _ExpectedExecutionGraphFakeAdapter
from memorii.tools.benchmark_suites.runtime_dependencies import BenchmarkRuntimeDependencies
from memorii.tools.run_live_llm_eval import _validate_live_safety

SUITE_NAME = "execution_graph_v1"


def _decision_mode(mode: str) -> DecisionModeName:
    if mode in {"auto", "rule", "llm", "hybrid"}:
        return cast(DecisionModeName, mode)
    raise ValueError(f"Unsupported execution graph mode: {mode}")


def _load_execution_graph_suite(suite: str) -> tuple[list[ExecutionGraphScenario], str]:
    if suite == SUITE_NAME:
        return (
            load_execution_graph_v1_fixture_set(),
            "memorii.core.benchmark.fixture_sets.execution_graph_v1",
        )
    raise ValueError(f"Unsupported execution graph benchmark suite: {suite}")

def _run_execution_graph_transitions(
    *,
    scenarios: list[ExecutionGraphScenario],
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
    if effective_mode in {"llm", "hybrid"}:
        client = dependencies.eval_fake_client_cls() if dry_run else dependencies.llm_client_factory.from_config(runtime_config)
        runner = PromptLLMRunner(client=client, config=runtime_config)
        adapter = (
            _ExpectedExecutionGraphFakeAdapter(scenarios=scenarios, registry=registry)
            if dry_run and dependencies.is_default_fake_client()
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
            metadata: dict[str, object] = {
                "suite": "execution_graph_v1",
                "scenario_id": scenario.scenario_id,
                "decision_mode": mode,
                "transition_type": "execution_graph_decision",
            }
            llm_result = adapter.decide(
                context,
                request_id=request_id,
                metadata=metadata,
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

def _run_execution_graph_suite(
    args: argparse.Namespace,
    *,
    prompt_root: Path,
    dependencies: BenchmarkRuntimeDependencies,
) -> int:
    scenarios, fixture_source = _load_execution_graph_suite(SUITE_NAME)
    modes = ["rule", "llm", "hybrid"] if args.mode == "all" else [args.mode]
    for mode in modes:
        rows, llm_rows = _run_execution_graph_transitions(
            scenarios=scenarios,
            mode=mode,
            dry_run=args.dry_run,
            allow_live=args.allow_live,
            prompt_root=prompt_root,
            dependencies=dependencies,
        )
        run_dir = _write_execution_graph_artifacts(
            scenarios=scenarios,
            rows=rows,
            llm_rows=llm_rows,
            suite=SUITE_NAME,
            mode=mode,
            storage_root=args.storage_root,
            fixture_source=fixture_source,
        )
        _print_execution_graph_summary(
            suite=SUITE_NAME,
            mode=mode,
            run_dir=run_dir,
            rows=rows,
            llm_rows=llm_rows,
        )
    return 0



def run(args: argparse.Namespace, prompt_root: Path, *, dependencies: BenchmarkRuntimeDependencies) -> int:
    require_memorii_only(args, SUITE_NAME)
    return _run_execution_graph_suite(args, prompt_root=prompt_root, dependencies=dependencies)


def build_runner(*, dependencies: BenchmarkRuntimeDependencies) -> BenchmarkSuiteRunner:
    return FunctionBenchmarkSuiteRunner(
        SUITE_NAME,
        lambda args, prompt_root: run(args, prompt_root, dependencies=dependencies),
        ALL_DECISION_MODES,
    )
