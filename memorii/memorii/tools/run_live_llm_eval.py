from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from memorii.core.llm_config import LLMLiveTestConfig, LLMRuntimeConfig
from memorii.core.llm_decision.adapters import (
    LLMBeliefUpdateAdapter,
    LLMPromotionDecisionAdapter,
)
from memorii.core.llm_decision.models import EvalSnapshot, LLMDecisionMode
from memorii.core.llm_eval.golden import belief_golden_v1, promotion_golden_v1
from memorii.core.llm_eval.models import EvalRunReport
from memorii.core.llm_eval.runner import OfflineLLMEvalRunner
from memorii.core.llm_trace.policy import LLMTracePolicy
from memorii.core.llm_provider.factory import LLMClientFactory
from memorii.core.llm_provider.models import LLMStructuredRequest, LLMStructuredResponse
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.prompts.registry import PromptRegistry


class EvalFakeClient:
    provider_name = "fake"

    def complete_structured(
        self,
        request: LLMStructuredRequest,
        *,
        config: LLMRuntimeConfig,
    ) -> LLMStructuredResponse:
        del config
        if request.prompt_ref == "promotion_decision:v1":
            raw = json.dumps(
                {
                    "promote": False,
                    "target_plane": None,
                    "confidence": 0.5,
                    "rationale": "dry run",
                    "failure_mode": None,
                    "requires_judge_review": True,
                },
                sort_keys=True,
            )
        elif request.prompt_ref == "belief_update:v1":
            raw = json.dumps(
                {
                    "belief": 0.5,
                    "confidence": 0.5,
                    "rationale": "dry run",
                    "failure_mode": None,
                    "requires_judge_review": True,
                },
                sort_keys=True,
            )
        else:
            raw = "{}"

        return LLMStructuredResponse(
            request_id=request.request_id,
            provider=self.provider_name,
            raw_text=raw,
            valid_json=False,
            schema_valid=False,
        )


def _load_snapshots(golden_set: str) -> list[EvalSnapshot]:
    if golden_set == "promotion":
        return promotion_golden_v1()
    if golden_set == "belief":
        return belief_golden_v1()
    return [*promotion_golden_v1(), *belief_golden_v1()]


def _requested_modes(mode_arg: str) -> list[str]:
    if mode_arg == "all":
        return ["rule", "llm", "hybrid"]
    return [mode_arg]


def _validate_live_safety(
    *,
    modes: list[str],
    dry_run: bool,
    allow_live: bool,
    runtime_config: LLMRuntimeConfig,
    live_config: LLMLiveTestConfig,
) -> None:
    if dry_run:
        return

    requires_live_llm = any(mode in {"llm", "hybrid"} for mode in modes)
    if not requires_live_llm:
        return

    provider = runtime_config.provider.strip().lower()
    if provider in {"none", "fake"}:
        raise SystemExit(
            "Refusing run: modes include llm/hybrid but provider is none/fake. "
            "Use a real provider or pass --dry-run."
        )
    if not allow_live:
        raise SystemExit(
            "Refusing live LLM calls: modes include llm/hybrid and --allow-live was not set."
        )
    if not live_config.should_run_live_llm_tests(runtime_config):
        raise SystemExit(
            "Refusing live LLM calls: LLMLiveTestConfig gate failed. "
            "Require MEMORII_ENABLE_LIVE_LLM_TESTS=true, non-none/fake provider, and API key."
        )


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _sanitize_run_id(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_." else "_" for char in value)


def _write_artifacts(
    *,
    storage_root: Path,
    report: EvalRunReport,
    snapshots: list[EvalSnapshot],
    provider: str,
    model: str | None,
    golden_set: str,
    mode: str,
) -> Path:
    run_dir = (
        storage_root
        / "eval_runs"
        / "llm"
        / datetime.now(UTC).strftime("%Y-%m-%d")
        / _sanitize_run_id(report.run_id)
    )

    if run_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing artifact directory: {run_dir}")

    (run_dir / "inputs").mkdir(parents=True, exist_ok=False)

    (run_dir / "report.json").write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_jsonl(run_dir / "results.jsonl", [result.model_dump(mode="json") for result in report.results])
    _write_jsonl(
        run_dir / "failures.jsonl",
        [result.model_dump(mode="json") for result in report.results if not result.passed],
    )
    _write_jsonl(
        run_dir / "fallbacks.jsonl",
        [result.model_dump(mode="json") for result in report.results if result.fallback_used],
    )
    _write_jsonl(
        run_dir / "disagreements.jsonl",
        [result.model_dump(mode="json") for result in report.results if result.disagreement],
    )
    _write_jsonl(run_dir / "inputs" / "snapshots.jsonl", [snapshot.model_dump(mode="json") for snapshot in snapshots])

    fallback_cases = sum(1 for result in report.results if result.fallback_used)
    disagreement_cases = sum(1 for result in report.results if result.disagreement)
    requires_review_cases = sum(1 for result in report.results if result.requires_judge_review)

    summary = (
        f"run_id: {report.run_id}\n"
        f"provider: {provider}\n"
        f"model: {model}\n"
        f"golden_set: {golden_set}\n"
        f"mode: {mode}\n"
        f"total_cases: {report.total_cases}\n"
        f"passed_cases: {report.passed_cases}\n"
        f"failed_cases: {report.failed_cases}\n"
        f"fallback_cases: {fallback_cases}\n"
        f"disagreement_cases: {disagreement_cases}\n"
        f"requires_judge_review_cases: {requires_review_cases}\n"
    )
    (run_dir / "summary.txt").write_text(summary, encoding="utf-8")
    return run_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden-set", choices=["promotion", "belief", "all"], default="all")
    parser.add_argument("--mode", choices=["rule", "llm", "hybrid", "all"], default="all")
    parser.add_argument("--storage-root", default=".memorii")
    parser.add_argument("--prompt-root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-live", action="store_true")
    parser.add_argument("--trace-successes", action="store_true")
    parser.add_argument("--no-trace-failures", action="store_true")
    parser.add_argument("--no-trace-fallbacks", action="store_true")
    parser.add_argument("--no-trace-disagreements", action="store_true")
    parser.add_argument("--no-trace-human-review", action="store_true")
    parser.add_argument("--min-judge-score-to-keep", type=float, default=None)
    args = parser.parse_args(argv)

    runtime_config = LLMRuntimeConfig.from_env()
    live_config = LLMLiveTestConfig.from_env()
    print(f"runtime_config={runtime_config.redacted_dict()}")

    modes = _requested_modes(args.mode)
    _validate_live_safety(
        modes=modes,
        dry_run=args.dry_run,
        allow_live=args.allow_live,
        runtime_config=runtime_config,
        live_config=live_config,
    )

    prompt_root = Path(args.prompt_root) if args.prompt_root else Path(__file__).resolve().parents[2] / "prompts"

    client = EvalFakeClient() if args.dry_run else LLMClientFactory.from_config(runtime_config)
    runner = PromptLLMRunner(client=client, config=runtime_config)
    registry = PromptRegistry(prompt_root=prompt_root)
    promotion_adapter = LLMPromotionDecisionAdapter(runner=runner, registry=registry)
    belief_adapter = LLMBeliefUpdateAdapter(runner=runner, registry=registry)

    snapshots = _load_snapshots(args.golden_set)
    trace_policy = LLMTracePolicy(
        trace_successes=args.trace_successes,
        trace_failures=not args.no_trace_failures,
        trace_fallbacks=not args.no_trace_fallbacks,
        trace_disagreements=not args.no_trace_disagreements,
        trace_human_review=not args.no_trace_human_review,
        min_judge_score_to_keep=args.min_judge_score_to_keep,
    )
    for mode in modes:
        report = OfflineLLMEvalRunner(
            promotion_llm_adapter=promotion_adapter,
            belief_llm_adapter=belief_adapter,
            decision_mode=LLMDecisionMode(mode),
            trace_policy=trace_policy,
        ).run_snapshots(snapshots)
        assert isinstance(report, EvalRunReport)
        run_dir = _write_artifacts(
            storage_root=Path(args.storage_root),
            report=report,
            snapshots=snapshots,
            provider=runtime_config.provider,
            model=runtime_config.model,
            golden_set=args.golden_set,
            mode=mode,
        )
        print(
            f"mode={mode} total_cases={report.total_cases} "
            f"passed={report.passed_cases} failed={report.failed_cases} artifacts={run_dir}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
