"""Official HotpotQA benchmark suite runner."""

from __future__ import annotations

import argparse
import json
from datetime import (
    UTC,
    datetime,
)
from pathlib import Path
from typing import cast

from memorii.core.benchmark.hotpotqa import (
    HotpotQAExample,
    load_hotpotqa_examples,
    select_hotpotqa_subset,
)
from memorii.core.benchmark.hotpotqa_official import (
    HotpotQAPrediction,
    build_hotpotqa_error_analysis,
    build_hotpotqa_stage_diagnostics,
    evaluate_hotpotqa_predictions,
    hotpotqa_answer_format_diagnostic,
    hotpotqa_evidence_context_for_example,
    hotpotqa_supporting_fact_candidate_ids,
    hotpotqa_supporting_fact_pairs_from_candidate_ids,
    score_hotpotqa_example,
)
from memorii.core.benchmark.models import BenchmarkRunConfig
from memorii.core.benchmark.reproducibility import build_run_id
from memorii.core.env_config import load_memorii_environment
from memorii.core.grounding.models import EvidenceSelectionDecision
from memorii.core.grounding.pipeline import GroundedAnswerPipeline
from memorii.core.llm_config import (
    DecisionModeName,
    LLMDecisionRuntimeConfig,
    LLMLiveTestConfig,
    LLMRuntimeConfig,
)
from memorii.core.llm_decision.adapters import (
    LLMAnswerVerificationAdapter,
    LLMEvidenceSelectionAdapter,
    LLMGroundedAnswerAdapter,
)
from memorii.core.llm_decision.models import LLMDecisionMode
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.prompts.registry import PromptRegistry
from memorii.tools.benchmark_registry import BenchmarkSuiteRunner, FunctionBenchmarkSuiteRunner
from memorii.tools.benchmark_suites.artifact_io import _write_jsonl
from memorii.tools.benchmark_suites.common import ALL_DECISION_MODES, require_memorii_only
from memorii.tools.benchmark_suites.fake_adapters import (
    _ExpectedHotpotQAAnswerVerificationFakeAdapter,
    _ExpectedHotpotQAEvidenceSelectionFakeAdapter,
    _ExpectedHotpotQAGroundedAnswerFakeAdapter,
)
from memorii.tools.benchmark_suites.runtime_dependencies import BenchmarkRuntimeDependencies
from memorii.tools.run_live_llm_eval import _validate_live_safety

SUITE_NAME = "hotpotqa_official_v1"


def _load_hotpotqa_official_examples(args: argparse.Namespace) -> list[HotpotQAExample]:
    examples = load_hotpotqa_examples(args.hotpotqa_dataset, split=args.hotpotqa_split)
    return select_hotpotqa_subset(
        examples,
        dataset_source=str(args.hotpotqa_dataset),
        split=args.hotpotqa_split,
        seed=args.seed,
        subset_size=args.hotpotqa_subset_size,
        question_type=args.hotpotqa_question_type,
    )

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


def _decision_modes_from_args(mode: str) -> list[DecisionModeName]:
    if mode == "all":
        return ["rule", "llm", "hybrid"]
    if mode in {"auto", "rule", "llm", "hybrid"}:
        return [cast(DecisionModeName, mode)]
    raise ValueError(f"Unsupported HotpotQA mode: {mode}")


def _trace_input_payload(row: dict[str, object]) -> dict[str, object]:
    trace = row.get("trace")
    if not isinstance(trace, dict):
        return {}
    payload = trace.get("input_payload")
    return payload if isinstance(payload, dict) else {}

def _run_hotpotqa_answer_decisions(
    *,
    examples: list[HotpotQAExample],
    mode: DecisionModeName,
    dry_run: bool,
    allow_live: bool,
    prompt_root: Path,
    dependencies: BenchmarkRuntimeDependencies,
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
        client = dependencies.eval_fake_client_cls() if dry_run else dependencies.llm_client_factory.from_config(runtime_config)
        runner = PromptLLMRunner(client=client, config=runtime_config)
        if dry_run and dependencies.is_default_fake_client():
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
                "candidate_titles": sorted({candidate.title for candidate in context.candidates if candidate.title is not None}),
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
    examples: list[HotpotQAExample],
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
                str(_trace_input_payload(row).get("prompt_hash"))
                for row in llm_rows
                if _trace_input_payload(row).get("prompt_hash") is not None
            }
        ),
        "models": sorted(
            {
                str(_trace_input_payload(row).get("model"))
                for row in llm_rows
                if _trace_input_payload(row).get("model") is not None
            }
        ),
        "providers": sorted(
            {
                str(_trace_input_payload(row).get("provider"))
                for row in llm_rows
                if _trace_input_payload(row).get("provider") is not None
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
    stage_rows = stage_diagnostics.get("rows", [])
    _write_jsonl(run_dir / "hotpotqa_stage_diagnostics.jsonl", stage_rows if isinstance(stage_rows, list) else [])
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
    examples: list[HotpotQAExample],
    mode: DecisionModeName,
    dry_run: bool,
    allow_live: bool,
    prompt_root: Path,
    dependencies: BenchmarkRuntimeDependencies,
    run_dir: Path,
    official_answer_rows: list[dict[str, object]],
) -> None:
    gold_evidence_prediction, gold_evidence_rows, _, gold_evidence_llm_rows = _run_hotpotqa_answer_decisions(
        examples=examples,
        mode=mode,
        dry_run=dry_run,
        allow_live=allow_live,
        prompt_root=prompt_root,
        dependencies=dependencies,
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
        proof_id_values = row.get("proof_citation_candidate_ids", [])
        proof_ids = {str(value) for value in proof_id_values} if isinstance(proof_id_values, list) else set()
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
    examples: list[HotpotQAExample],
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

def _run_hotpotqa_official_suite(
    args: argparse.Namespace,
    *,
    prompt_root: Path,
    dependencies: BenchmarkRuntimeDependencies,
) -> int:
    examples = _load_hotpotqa_official_examples(args)
    modes = _decision_modes_from_args(args.mode)
    for mode in modes:
        prediction, answer_rows, retrieval_rows, llm_rows = _run_hotpotqa_answer_decisions(
            examples=examples,
            mode=mode,
            dry_run=args.dry_run,
            allow_live=args.allow_live,
            prompt_root=prompt_root,
            dependencies=dependencies,
        )
        metrics = evaluate_hotpotqa_predictions(prediction=prediction, gold_examples=examples)
        run_dir = _write_hotpotqa_official_artifacts(
            examples=examples,
            prediction=prediction,
            answer_rows=answer_rows,
            retrieval_rows=retrieval_rows,
            llm_rows=llm_rows,
            metrics=metrics,
            suite=SUITE_NAME,
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
                dependencies=dependencies,
                run_dir=run_dir,
                official_answer_rows=answer_rows,
            )
        _print_hotpotqa_official_summary(
            suite=SUITE_NAME,
            mode=mode,
            run_dir=run_dir,
            examples=examples,
            metrics=metrics,
            llm_rows=llm_rows,
        )
    return 0



def run(args: argparse.Namespace, prompt_root: Path, *, dependencies: BenchmarkRuntimeDependencies) -> int:
    require_memorii_only(args, SUITE_NAME)
    return _run_hotpotqa_official_suite(args, prompt_root=prompt_root, dependencies=dependencies)


def build_runner(*, dependencies: BenchmarkRuntimeDependencies) -> BenchmarkSuiteRunner:
    return FunctionBenchmarkSuiteRunner(
        SUITE_NAME,
        lambda args, prompt_root: run(args, prompt_root, dependencies=dependencies),
        ALL_DECISION_MODES,
    )
