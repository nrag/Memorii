from __future__ import annotations

import pytest

from memorii.core.benchmark.hotpotqa import HotpotContext, HotpotQAExample, load_hotpotqa_examples, select_hotpotqa_subset
from memorii.core.benchmark.hotpotqa_official import (
    HotpotQAPrediction,
    build_hotpotqa_error_analysis,
    build_hotpotqa_stage_diagnostics,
    evaluate_hotpotqa_predictions,
    expected_hotpotqa_grounding_decisions,
    hotpotqa_answer_format_diagnostic,
    hotpotqa_evidence_context_for_example,
    hotpotqa_supporting_fact_pairs_from_candidate_ids,
    score_hotpotqa_example,
)


def _example() -> HotpotQAExample:
    return HotpotQAExample(
        example_id="hp-official-1",
        question="Where was the author of Hamlet born?",
        answer="England",
        question_type="bridge",
        supporting_facts=[("Hamlet", 0), ("William Shakespeare", 0)],
        context=[
            HotpotContext(title="Hamlet", sentences=["Hamlet is a play by William Shakespeare."]),
            HotpotContext(title="William Shakespeare", sentences=["William Shakespeare was born in England."]),
        ],
    )


def test_hotpotqa_official_metrics_match_exact_prediction() -> None:
    example = _example()
    prediction = HotpotQAPrediction(
        answer={example.example_id: "England"},
        sp={example.example_id: [("Hamlet", 0), ("William Shakespeare", 0)]},
    )

    metrics = evaluate_hotpotqa_predictions(prediction=prediction, gold_examples=[example])

    assert metrics["em"] == 1.0
    assert metrics["f1"] == 1.0
    assert metrics["sp_em"] == 1.0
    assert metrics["sp_f1"] == 1.0
    assert metrics["joint_em"] == 1.0
    assert metrics["joint_f1"] == 1.0


def test_hotpotqa_official_answer_normalization_and_partial_support() -> None:
    example = _example()
    prediction = HotpotQAPrediction(
        answer={example.example_id: "the england!"},
        sp={example.example_id: [("Hamlet", 0), ("Distractor", 0)]},
    )

    metrics = evaluate_hotpotqa_predictions(prediction=prediction, gold_examples=[example])

    assert metrics["em"] == 1.0
    assert metrics["f1"] == 1.0
    assert metrics["sp_em"] == 0.0
    assert metrics["sp_prec"] == 0.5
    assert metrics["sp_recall"] == 0.5
    assert metrics["sp_f1"] == 0.5
    assert metrics["joint_f1"] == 0.5


def test_hotpotqa_official_yes_no_noanswer_behavior() -> None:
    example = _example().model_copy(update={"answer": "yes"})
    prediction = HotpotQAPrediction(
        answer={example.example_id: "no"},
        sp={example.example_id: [("Hamlet", 0), ("William Shakespeare", 0)]},
    )

    metrics = evaluate_hotpotqa_predictions(prediction=prediction, gold_examples=[example])

    assert metrics["em"] == 0.0
    assert metrics["f1"] == 0.0
    assert metrics["sp_f1"] == 1.0
    assert metrics["joint_f1"] == 0.0


def test_hotpotqa_answer_format_diagnostic_does_not_export_canonical_answers() -> None:
    diagnostic = hotpotqa_answer_format_diagnostic(
        raw_answer="Yes, both Billy and Barak are breeds of scenthound.",
        gold_answer="yes",
    )

    assert diagnostic["gold_is_binary"] is True
    assert diagnostic["raw_binary_prefix"] == "yes"
    assert diagnostic["binary_prefix_matches_gold"] is True
    assert diagnostic["verbose_binary_answer"] is True


def test_hotpotqa_evidence_context_round_trips_supporting_facts() -> None:
    example = _example()

    context = hotpotqa_evidence_context_for_example(example)
    evidence_selection, grounded_answer, verification = expected_hotpotqa_grounding_decisions(example)
    pairs = hotpotqa_supporting_fact_pairs_from_candidate_ids(
        example=example,
        candidate_ids=evidence_selection.selected_candidate_ids,
    )

    assert len(context.candidates) == 2
    assert pairs == example.supporting_facts
    assert grounded_answer.answer == example.answer
    assert evidence_selection.proof_steps
    assert verification.entailed is True


def test_hotpotqa_example_score_exposes_answer_support_and_joint_metrics() -> None:
    example = _example()

    score = score_hotpotqa_example(
        prediction_answer="the england!",
        prediction_supporting_facts=[("Hamlet", 0)],
        example=example,
    )

    assert score.answer_em == 1.0
    assert score.answer_f1 == 1.0
    assert score.support_em == 0.0
    assert score.support_precision == 1.0
    assert score.support_recall == 0.5
    assert score.support_f1 == pytest.approx(2 / 3)
    assert score.joint_f1 == pytest.approx(2 / 3)


def test_hotpotqa_error_analysis_summarizes_failure_buckets() -> None:
    example = _example()
    yes_example = _example().model_copy(
        update={
            "example_id": "hp-official-2",
            "answer": "yes",
            "question_type": "comparison",
        }
    )
    canonical_example = _example().model_copy(
        update={
            "example_id": "hp-official-3",
            "answer": "yes",
            "question_type": "comparison",
        }
    )
    extra_support_score = score_hotpotqa_example(
        prediction_answer="England",
        prediction_supporting_facts=[("Hamlet", 0), ("William Shakespeare", 0), ("Distractor", 0)],
        example=example,
    )
    wrong_answer_score = score_hotpotqa_example(
        prediction_answer="no",
        prediction_supporting_facts=[("Hamlet", 0), ("William Shakespeare", 0)],
        example=yes_example,
    )
    verbose_binary_score = score_hotpotqa_example(
        prediction_answer="Yes, both are supported.",
        prediction_supporting_facts=[("Hamlet", 0), ("William Shakespeare", 0)],
        example=canonical_example,
    )

    analysis = build_hotpotqa_error_analysis(
        examples=[example, yes_example, canonical_example],
        answer_rows=[
            {
                "example_id": example.example_id,
                "raw_answer": "England",
                "exported_answer": "England",
                "answer_format_diagnostic": hotpotqa_answer_format_diagnostic(raw_answer="England", gold_answer="England"),
                "predicted_supporting_facts": [("Hamlet", 0), ("William Shakespeare", 0), ("Distractor", 0)],
                "scores": extra_support_score.model_dump(mode="json"),
            },
            {
                "example_id": yes_example.example_id,
                "raw_answer": "No, they are not both supported.",
                "exported_answer": "No, they are not both supported.",
                "answer_format_diagnostic": hotpotqa_answer_format_diagnostic(
                    raw_answer="No, they are not both supported.",
                    gold_answer="yes",
                ),
                "predicted_supporting_facts": [("Hamlet", 0), ("William Shakespeare", 0)],
                "scores": wrong_answer_score.model_dump(mode="json"),
            },
            {
                "example_id": canonical_example.example_id,
                "raw_answer": "Yes, both are supported.",
                "exported_answer": "Yes, both are supported.",
                "answer_format_diagnostic": hotpotqa_answer_format_diagnostic(
                    raw_answer="Yes, both are supported.",
                    gold_answer="yes",
                ),
                "predicted_supporting_facts": [("Hamlet", 0), ("William Shakespeare", 0)],
                "scores": verbose_binary_score.model_dump(mode="json"),
            },
        ],
    )

    assert analysis["summary"]["examples"] == 3
    assert analysis["summary"]["support_extra_fact_examples"] == 1
    assert analysis["summary"]["answer_correct_support_wrong"] == 1
    assert analysis["summary"]["answer_wrong_support_correct"] == 2
    assert analysis["summary"]["binary_answer_format_maybe_cost_f1"] == 1
    assert analysis["by_question_type"]["bridge"]["support_f1_failures"] == 1
    assert analysis["by_question_type"]["comparison"]["answer_f1_failures"] == 2
    assert len(analysis["representative_failures"]) == 3


def test_hotpotqa_stage_diagnostics_summarizes_stage_coverage_and_failure_buckets() -> None:
    example = _example()
    support_bad_score = score_hotpotqa_example(
        prediction_answer="England",
        prediction_supporting_facts=[("Hamlet", 0)],
        example=example,
    )
    answer_bad_score = score_hotpotqa_example(
        prediction_answer="France",
        prediction_supporting_facts=[("Hamlet", 0), ("William Shakespeare", 0)],
        example=example,
    )

    diagnostics = build_hotpotqa_stage_diagnostics(
        examples=[example, example.model_copy(update={"example_id": "hp-official-2"})],
        answer_rows=[
            {
                "example_id": example.example_id,
                "scores": support_bad_score.model_dump(mode="json"),
                "proof_supporting_facts": [("Hamlet", 0), ("William Shakespeare", 0)],
                "answer_supporting_facts": [("Hamlet", 0)],
                "verified_supporting_facts": [("Hamlet", 0)],
                "predicted_supporting_facts": [("Hamlet", 0)],
                "verified": True,
                "answer_verification": {"question_constraints": [], "alternative_answers": []},
                "answer_finalization": {"rejected_reason": "no_corrected_answer"},
            },
            {
                "example_id": "hp-official-2",
                "scores": answer_bad_score.model_dump(mode="json"),
                "proof_supporting_facts": [("Hamlet", 0), ("William Shakespeare", 0)],
                "answer_supporting_facts": [("Hamlet", 0), ("William Shakespeare", 0)],
                "verified_supporting_facts": [("Hamlet", 0), ("William Shakespeare", 0)],
                "predicted_supporting_facts": [("Hamlet", 0), ("William Shakespeare", 0)],
                "verified": True,
                "answer_verification": {
                    "question_constraints": [{"satisfied": True, "candidate_ids": [("Hamlet", 0)]}],
                    "alternative_answers": [{"answer": "England"}],
                },
                "answer_finalization": {},
            },
        ],
    )

    summary = diagnostics["summary"]
    assert summary["examples"] == 2
    assert summary["proof_full_support_count"] == 2
    assert summary["final_citation_full_support_count"] == 1
    assert summary["proof_had_support_final_lost_support_count"] == 1
    assert summary["answer_correct_support_bad_count"] == 1
    assert summary["support_correct_answer_bad_count"] == 1
    assert summary["wrong_answer_verified_count"] == 1
    assert summary["no_alternative_challenge_count"] == 1
    assert diagnostics["rows"][0]["answer_bucket"] == "answer_ok_support_bad"


def test_hotpotqa_subset_size_zero_selects_all_examples(tmp_path) -> None:
    source = tmp_path / "hotpot_train_style.json"
    source.write_text(
        """
[
  {"_id": "a", "question": "A?", "answer": "A", "supporting_facts": [["A", 0]], "context": [["A", ["A."]]]},
  {"_id": "b", "question": "B?", "answer": "B", "supporting_facts": [["B", 0]], "context": [["B", ["B."]]]}
]
""".strip(),
        encoding="utf-8",
    )

    examples = load_hotpotqa_examples(source)
    selected = select_hotpotqa_subset(
        examples,
        dataset_source=str(source),
        split="train",
        seed=7,
        subset_size=0,
    )

    assert {example.example_id for example in selected} == {"a", "b"}
