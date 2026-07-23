"""Answer, hallucination, abstention, and confidence judges."""

from memorii.core.benchmark.memory_evolution_sim.schemas import (
    JudgeVerdict,
    JudgeVote,
    LatentGraphScenario,
    ObservabilityLabel,
    OracleCheckpoint,
    SimSystemOutput,
)
from memorii.core.benchmark.memory_evolution_sim.utils import (
    answer_bucket,
    hidden_answer_leaks,
    normalize_sim_text,
    role_claim_ids,
    role_entity_ids,
    role_relation_ids,
)


def judge_answer(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> JudgeVote:
    if not checkpoint.checkpoint_contract.answer_required:
        return JudgeVote(
            judge_id="answer_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.PASS,
            score=1.0,
            confidence=0.7,
            failure_buckets=(
                ["graph_answer_optional_missing"]
                if not output.answer and checkpoint.expected_answer
                else []
            ),
            rationale=(
                "answer text is diagnostic for this checkpoint; "
                "structured graph/action state is authoritative"
            ),
        )
    if checkpoint.expected_abstention:
        passed = output.answer in {None, "unknown"} or bool(output.uncertain_ids)
        verdict = JudgeVerdict.PASS if passed else JudgeVerdict.FAIL
        return JudgeVote(
            judge_id="ambiguity_answer_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=verdict,
            score=1.0 if passed else 0.0,
            confidence=0.8,
            failed_ids=[] if passed else checkpoint.expected_uncertain_ids,
            failure_buckets=[] if passed else ["ambiguous_fact_overcommitted"],
            rationale="abstention expectation checked",
        )
    if checkpoint.expected_answer is None and checkpoint.expected_next_action is None:
        return JudgeVote(
            judge_id="answer_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.ABSTAIN,
            score=1.0,
            confidence=0.2,
            failure_buckets=["judge_uncovered_case"],
            rationale="no answer expectation",
        )
    expected = checkpoint.expected_answer or checkpoint.expected_next_action or ""
    actual = output.next_action or "" if checkpoint.expected_next_action is not None else output.answer or ""
    passed = _answer_matches_expected(scenario, checkpoint, actual, expected)
    return JudgeVote(
        judge_id="answer_judge",
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=JudgeVerdict.PASS if passed else JudgeVerdict.FAIL,
        score=1.0 if passed else 0.0,
        confidence=0.9,
        failed_ids=[] if passed else [checkpoint.checkpoint_id],
        failure_buckets=[] if passed else [answer_bucket(checkpoint)],
        rationale="answer matched" if passed else f"answer {actual!r} did not match {expected!r}",
    )


def judge_hidden_hallucination(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> JudgeVote:
    hidden_ids = {
        item.entity_id for item in scenario.entities if item.observability == ObservabilityLabel.HIDDEN
    } | {
        item.claim_id for item in scenario.claims if item.observability == ObservabilityLabel.HIDDEN
    } | {
        item.relation_id for item in scenario.relations if item.observability == ObservabilityLabel.HIDDEN
    }
    asserted = set(role_entity_ids(output)) | set(role_claim_ids(output)) | set(role_relation_ids(output))
    hallucinated = sorted(asserted & hidden_ids)
    answer_leaks = hidden_answer_leaks(scenario, output)
    failed = [*hallucinated, *answer_leaks]
    buckets = []
    if hallucinated:
        buckets.append("hidden_fact_hallucinated")
    if answer_leaks:
        buckets.append("hidden_fact_answer_leak")
    return JudgeVote(
        judge_id="hidden_hallucination_judge",
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=JudgeVerdict.FAIL if failed else JudgeVerdict.PASS,
        score=0.0 if failed else 1.0,
        confidence=0.9,
        failed_ids=failed,
        failure_buckets=buckets,
        rationale="hidden facts asserted" if failed else "no hidden facts asserted",
    )


def judge_ambiguity_abstention(checkpoint: OracleCheckpoint, output: SimSystemOutput) -> JudgeVote:
    if not checkpoint.expected_uncertain_ids:
        return JudgeVote(
            judge_id="ambiguity_abstention_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.ABSTAIN,
            score=1.0,
            confidence=0.2,
            failure_buckets=["judge_uncovered_case"],
            rationale="no ambiguity expectation",
        )
    overcommitted = [
        item
        for item in checkpoint.expected_uncertain_ids
        if item in role_entity_ids(output)
        or item in role_claim_ids(output)
        or item in role_relation_ids(output)
    ]
    if output.confidence >= 0.75 and overcommitted:
        return JudgeVote(
            judge_id="ambiguity_abstention_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.FAIL,
            score=0.0,
            confidence=0.85,
            failed_ids=overcommitted,
            failure_buckets=["ambiguous_fact_overcommitted"],
            rationale="high-confidence assertion of ambiguous ids",
        )
    return JudgeVote(
        judge_id="ambiguity_abstention_judge",
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=JudgeVerdict.PASS,
        score=1.0,
        confidence=0.75,
        covered_ids=checkpoint.expected_uncertain_ids,
        rationale="ambiguous ids were not overcommitted",
    )


def judge_confidence_calibration(checkpoint: OracleCheckpoint, output: SimSystemOutput) -> JudgeVote:
    if checkpoint.expected_abstention and output.confidence > 0.55:
        return JudgeVote(
            judge_id="confidence_calibration_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.FAIL,
            score=0.0,
            confidence=0.8,
            failure_buckets=["overconfident_wrong_answer"],
            rationale="abstention checkpoint returned high confidence",
        )
    return JudgeVote(
        judge_id="confidence_calibration_judge",
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=JudgeVerdict.PASS,
        score=1.0,
        confidence=0.7,
        rationale="confidence is within expected range",
    )


def _answer_matches_expected(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    actual: str,
    expected: str,
) -> bool:
    actual_norm = normalize_sim_text(actual)
    expected_norm = normalize_sim_text(expected)
    if expected_norm in actual_norm or actual_norm in expected_norm:
        return True
    expected_entity_ids = set(checkpoint.expected_entity_ids)
    for entity in scenario.entities:
        if entity.entity_id not in expected_entity_ids:
            continue
        names = {entity.canonical_name, *[alias.alias_text for alias in entity.aliases]}
        if any(normalize_sim_text(name) and normalize_sim_text(name) in actual_norm for name in names):
            return True
    return False
