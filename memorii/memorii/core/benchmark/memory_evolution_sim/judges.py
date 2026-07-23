"""Programmatic simulator judges."""

from __future__ import annotations

from memorii.core.benchmark.memory_evolution_sim.answer_judges import (
    judge_ambiguity_abstention,
    judge_answer,
    judge_confidence_calibration,
    judge_hidden_hallucination,
)
from memorii.core.benchmark.memory_evolution_sim.judge_features import (
    expected_rejected_claim_subject_entity_ids,
    rejected_required_definition_claim_ids,
    required_selected_entity_ids_for_policy,
    selected_action_state_event_ids_missing_support,
    selected_claim_evidence_event_ids_missing_support,
    selected_claim_ids_missing_support,
    selected_claim_support_closure_errors,
)
from memorii.core.benchmark.memory_evolution_sim.schemas import (
    JudgeAggregate,
    JudgeVerdict,
    JudgeVote,
    LatentGraphScenario,
    OracleCheckpoint,
    SimSystemOutput,
)
from memorii.core.benchmark.memory_evolution_sim.support_judges import (
    judge_supporting_evidence_precision,
)
from memorii.core.benchmark.memory_evolution_sim.utils import (
    claim_bucket,
    is_visible_claim,
    is_visible_entity,
    ordered_unique,
    relation_bucket,
    required_definition_claim_ids_for_selected_claims,
    role_relation_ids,
    selected_noncurrent_claim_ids,
)


def judge_sim_checkpoint(
    *,
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> JudgeAggregate:
    expected_entity_ids = _judge_expected_entity_ids(checkpoint)
    expected_claim_ids = _judge_expected_claim_ids(checkpoint)
    expected_citation_event_ids = _judge_expected_citation_event_ids(checkpoint)
    votes = [
        _set_judge(
            "entity_identity_judge",
            checkpoint,
            expected=expected_entity_ids,
            actual=output.selected_entity_ids,
            bucket="entity_alias_error",
        ),
        _set_judge(
            "entity_type_judge",
            checkpoint,
            expected=expected_entity_ids,
            actual=output.selected_entity_ids,
            bucket="entity_type_missing",
        ),
        _set_judge(
            "alias_resolution_judge",
            checkpoint,
            expected=expected_entity_ids,
            actual=output.selected_entity_ids,
            bucket="entity_alias_error",
        ),
        _selected_entity_role_judge(scenario, checkpoint, output),
        _set_judge(
            "claim_spo_judge",
            checkpoint,
            expected=expected_claim_ids,
            actual=output.selected_claim_ids,
            bucket=claim_bucket(checkpoint),
        ),
        _set_judge(
            "claim_lifecycle_judge",
            checkpoint,
            expected=expected_claim_ids,
            actual=output.selected_claim_ids,
            bucket=claim_bucket(checkpoint),
        ),
        _set_judge(
            "temporal_truth_judge",
            checkpoint,
            expected=expected_claim_ids,
            actual=output.selected_claim_ids,
            bucket="historical_truth_lost"
            if checkpoint.checkpoint_type == "historical_truth"
            else "wrong_current_truth",
        ),
        _set_judge(
            "source_trust_judge",
            checkpoint,
            expected=expected_claim_ids,
            actual=output.selected_claim_ids,
            bucket="source_trust_inversion",
        ),
        _set_judge(
            "modality_suppression_judge",
            checkpoint,
            expected=expected_claim_ids,
            actual=output.selected_claim_ids,
            bucket="modality_false_positive",
        ),
        _set_judge(
            "relation_directionality_judge",
            checkpoint,
            expected=checkpoint.expected_relation_ids,
            actual=role_relation_ids(output),
            bucket=relation_bucket(checkpoint),
        ),
        _set_judge(
            "support_contradiction_judge",
            checkpoint,
            expected=checkpoint.expected_relation_ids,
            actual=role_relation_ids(output),
            bucket=relation_bucket(checkpoint),
        ),
        _set_judge(
            "scope_judge",
            checkpoint,
            expected=expected_claim_ids,
            actual=output.selected_claim_ids,
            bucket="scope_leak",
        ),
        _set_judge(
            "belief_ranking_judge",
            checkpoint,
            expected=expected_claim_ids,
            actual=(
                output.belief_ranking_ids
                if checkpoint.checkpoint_type == "belief_ranking"
                else output.selected_claim_ids
            ),
            bucket="belief_ranking_error",
        ),
        _execution_branch_judge(checkpoint, output),
        _set_judge(
            "provenance_judge",
            checkpoint,
            expected=expected_citation_event_ids,
            actual=output.supporting_citation_event_ids,
            bucket="missing_provenance",
        ),
        _selected_truth_precision_judge(scenario, checkpoint, output),
        judge_supporting_evidence_precision(scenario, checkpoint, output),
        _selected_support_closure_judge(scenario, checkpoint, output),
        _rejection_classification_judge(scenario, checkpoint, output),
        _graph_context_judge(scenario, checkpoint, output),
        _definition_coverage_judge(scenario, checkpoint, output),
        judge_answer(scenario, checkpoint, output),
        judge_hidden_hallucination(scenario, checkpoint, output),
        judge_ambiguity_abstention(checkpoint, output),
        judge_confidence_calibration(checkpoint, output),
    ]
    required = set(checkpoint.required_judge_ids or _required_judge_ids_for_checkpoint(checkpoint))
    failed = [vote for vote in votes if vote.verdict == JudgeVerdict.FAIL]
    required_failed = [vote for vote in failed if vote.judge_id in required]
    required_abstained = [vote for vote in votes if vote.judge_id in required and vote.verdict == JudgeVerdict.ABSTAIN]
    optional_failed = [vote for vote in failed if vote.judge_id not in required]
    critical = sorted(
        {
            bucket
            for vote in [*required_failed, *required_abstained]
            for bucket in (vote.failure_buckets or ["judge_uncovered_case"])
        }
    )
    score = sum(vote.score for vote in votes) / len(votes)
    verdict = JudgeVerdict.FAIL if critical else JudgeVerdict.PASS
    verdict_set = {vote.verdict for vote in votes if vote.verdict != JudgeVerdict.ABSTAIN}
    review_required = bool(critical or optional_failed or len(verdict_set) > 1)
    return JudgeAggregate(
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=verdict,
        score=score,
        confidence=max(0.0, min(1.0, 1.0 - len(required_failed) / max(1, len(required)))),
        votes=votes,
        required_judge_ids=sorted(required),
        critical_failure_buckets=critical,
        review_required=review_required,
        rationale="; ".join(vote.rationale for vote in [*required_failed, *required_abstained, *optional_failed])
        or "required judges passed",
    )


def _judge_expected_entity_ids(checkpoint: OracleCheckpoint) -> list[str]:
    if checkpoint.checkpoint_type == "execution_continuation":
        return list(checkpoint.expected_execution_entity_ids)
    return list(checkpoint.expected_entity_ids)


def _judge_expected_claim_ids(checkpoint: OracleCheckpoint) -> list[str]:
    if checkpoint.checkpoint_type == "execution_continuation":
        return list(checkpoint.expected_execution_claim_ids)
    return list(checkpoint.expected_claim_ids)


def _judge_expected_citation_event_ids(checkpoint: OracleCheckpoint) -> list[str]:
    if checkpoint.checkpoint_type == "execution_continuation":
        return list(checkpoint.expected_execution_citation_event_ids)
    return list(checkpoint.expected_citation_event_ids)


def _required_judge_ids_for_checkpoint(checkpoint: OracleCheckpoint) -> list[str]:
    required = {
        "entity_identity_judge",
        "claim_spo_judge",
        "provenance_judge",
        "answer_judge",
        "hidden_hallucination_judge",
        "confidence_calibration_judge",
    }
    by_type = {
        "entity_reconstruction": {
            "entity_type_judge",
            "alias_resolution_judge",
            "relation_directionality_judge",
            "graph_context_judge",
            "definition_coverage_judge",
            "selected_truth_precision_judge",
        },
        "current_truth": {
            "temporal_truth_judge",
            "claim_lifecycle_judge",
            "selected_entity_role_judge",
            "selected_truth_precision_judge",
            "supporting_evidence_precision_judge",
        },
        "historical_truth": {
            "temporal_truth_judge",
            "claim_lifecycle_judge",
            "selected_entity_role_judge",
            "supporting_evidence_precision_judge",
        },
        "scoped_truth": {
            "scope_judge",
            "selected_entity_role_judge",
            "selected_truth_precision_judge",
            "supporting_evidence_precision_judge",
        },
        "source_trust_conflict": {
            "source_trust_judge",
            "support_contradiction_judge",
            "relation_directionality_judge",
            "selected_entity_role_judge",
            "selected_truth_precision_judge",
            "supporting_evidence_precision_judge",
        },
        "modality_suppression": {
            "modality_suppression_judge",
            "selected_entity_role_judge",
            "selected_truth_precision_judge",
            "supporting_evidence_precision_judge",
        },
        "entity_disambiguation": {
            "alias_resolution_judge",
            "selected_entity_role_judge",
            "selected_truth_precision_judge",
            "supporting_evidence_precision_judge",
        },
        "entity_split_repair": {
            "alias_resolution_judge",
            "graph_context_judge",
            "selected_entity_role_judge",
            "selected_truth_precision_judge",
            "supporting_evidence_precision_judge",
        },
        "claim_rekey": {
            "alias_resolution_judge",
            "claim_lifecycle_judge",
            "graph_context_judge",
            "definition_coverage_judge",
            "selected_entity_role_judge",
            "selected_truth_precision_judge",
        },
        "belief_ranking": {"belief_ranking_judge", "support_contradiction_judge", "selected_truth_precision_judge"},
        "execution_continuation": {
            "execution_branch_judge",
            "selected_truth_precision_judge",
            "supporting_evidence_precision_judge",
        },
        "abstention": {"ambiguity_abstention_judge"},
    }
    required.update(by_type.get(checkpoint.checkpoint_type, set()))
    if checkpoint.expected_uncertain_ids:
        required.add("ambiguity_abstention_judge")
    if checkpoint.expected_relation_ids:
        required.add("relation_directionality_judge")
    if checkpoint.expected_excluded_claim_ids or checkpoint.expected_excluded_entity_ids:
        required.add("rejection_classification_judge")
    if (
        _judge_expected_claim_ids(checkpoint)
        and checkpoint.task_contract.supporting_citations_must_be_direct_current_evidence
    ):
        required.add("selected_support_closure_judge")
    if _judge_expected_claim_ids(checkpoint):
        required.add("supporting_evidence_precision_judge")
    return sorted(required)


def _set_judge(
    judge_id: str,
    checkpoint: OracleCheckpoint,
    *,
    expected: list[str],
    actual: list[str],
    bucket: str,
) -> JudgeVote:
    if not expected:
        return JudgeVote(
            judge_id=judge_id,
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.ABSTAIN,
            score=1.0,
            confidence=0.2,
            rationale="judge uncovered for this checkpoint",
            failure_buckets=["judge_uncovered_case"],
        )
    missing = [item for item in expected if item not in actual]
    extra = [item for item in actual if item not in expected]
    if missing:
        return JudgeVote(
            judge_id=judge_id,
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.FAIL,
            score=0.0,
            confidence=0.9,
            covered_ids=[item for item in expected if item in actual],
            failed_ids=missing,
            failure_buckets=[bucket],
            rationale=f"missing expected ids: {missing}",
        )
    score = 1.0 if not extra else max(0.6, len(expected) / (len(expected) + len(extra)))
    return JudgeVote(
        judge_id=judge_id,
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=JudgeVerdict.PASS,
        score=score,
        confidence=0.85,
        covered_ids=list(expected),
        failure_buckets=["extra_provenance_noise"] if judge_id == "provenance_judge" and extra else [],
        rationale="expected ids covered",
    )


def _selected_entity_role_judge(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> JudgeVote:
    policy = checkpoint.task_contract.selected_entity_role_policy
    if policy == "audit_graph_entities":
        return JudgeVote(
            judge_id="selected_entity_role_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.PASS,
            score=1.0,
            confidence=0.8,
            rationale="audit graph entity role policy allows broader selected graph entities",
        )
    required_ids = required_selected_entity_ids_for_policy(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
        policy=policy,
    )
    if not required_ids:
        if checkpoint.expected_claim_ids:
            return JudgeVote(
                judge_id="selected_entity_role_judge",
                checkpoint_id=checkpoint.checkpoint_id,
                verdict=JudgeVerdict.FAIL,
                score=0.0,
                confidence=0.85,
                failed_ids=list(checkpoint.expected_entity_ids),
                failure_buckets=["entity_role_mismatch"],
                rationale="selected claims do not expose the entity role required by checkpoint contract",
            )
        return JudgeVote(
            judge_id="selected_entity_role_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.ABSTAIN,
            score=1.0,
            confidence=0.2,
            rationale="judge uncovered for this checkpoint",
            failure_buckets=["judge_uncovered_case"],
        )
    missing = [entity_id for entity_id in required_ids if entity_id not in output.selected_entity_ids]
    if missing:
        return JudgeVote(
            judge_id="selected_entity_role_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.FAIL,
            score=0.0,
            confidence=0.9,
            covered_ids=[entity_id for entity_id in required_ids if entity_id in output.selected_entity_ids],
            failed_ids=missing,
            failure_buckets=["entity_role_mismatch"],
            rationale=f"selected_entity_ids must include {policy} entity ids for selected claims: {missing}",
        )
    return JudgeVote(
        judge_id="selected_entity_role_judge",
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=JudgeVerdict.PASS,
        score=1.0,
        confidence=0.9,
        covered_ids=required_ids,
        rationale="selected entity roles match selected claim roles",
    )


def _selected_truth_precision_judge(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> JudgeVote:
    rejected_required_definition_claims = rejected_required_definition_claim_ids(scenario, output)
    bad_claims = selected_noncurrent_claim_ids(scenario, checkpoint, output)
    selected_excluded_claims = [
        item for item in checkpoint.expected_excluded_claim_ids if item in output.selected_claim_ids
    ]
    selected_excluded_entities = [
        item for item in checkpoint.expected_excluded_entity_ids if item in output.selected_entity_ids
    ]
    selected_rejected_claims = [item for item in output.selected_claim_ids if item in output.rejected_claim_ids]
    failed = ordered_unique(
        [
            *bad_claims,
            *selected_excluded_claims,
            *selected_excluded_entities,
            *selected_rejected_claims,
            *rejected_required_definition_claims,
        ]
    )
    if failed:
        buckets = ["selected_truth_precision_error"]
        if selected_rejected_claims:
            buckets.append("selected_rejected_channel_overlap")
        if rejected_required_definition_claims:
            buckets.append("definition_claim_rejected")
        return JudgeVote(
            judge_id="selected_truth_precision_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.FAIL,
            score=0.0,
            confidence=0.9,
            failed_ids=failed,
            failure_buckets=ordered_unique(buckets),
            rationale=f"selected channel contains non-current or excluded ids: {failed}",
        )
    return JudgeVote(
        judge_id="selected_truth_precision_judge",
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=JudgeVerdict.PASS,
        score=1.0,
        confidence=0.85,
        rationale="selected channel contains no excluded or non-current ids",
    )


def _selected_support_closure_judge(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> JudgeVote:
    if not checkpoint.task_contract.supporting_citations_must_be_direct_current_evidence:
        return JudgeVote(
            judge_id="selected_support_closure_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.ABSTAIN,
            score=1.0,
            confidence=0.2,
            failure_buckets=["judge_uncovered_case"],
            rationale="support closure is not required by checkpoint contract",
        )
    if not output.selected_claim_ids:
        return JudgeVote(
            judge_id="selected_support_closure_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.ABSTAIN,
            score=1.0,
            confidence=0.2,
            failure_buckets=["judge_uncovered_case"],
            rationale="no selected claims to check for support closure",
        )
    closure_errors = selected_claim_support_closure_errors(scenario, output)
    missing_support_claims = selected_claim_ids_missing_support(closure_errors)
    missing_evidence_event_ids = selected_claim_evidence_event_ids_missing_support(closure_errors)
    action_claims_missing_support = [
        error.claim_id for error in closure_errors if error.is_action_state and error.missing_supporting_claim
    ]
    action_events_missing = selected_action_state_event_ids_missing_support(closure_errors)
    failed = ordered_unique([*missing_support_claims, *missing_evidence_event_ids])
    if failed:
        buckets: list[str] = []
        if missing_support_claims:
            buckets.append("selected_claim_support_missing")
        if missing_evidence_event_ids:
            buckets.append("selected_claim_provenance_missing")
        if checkpoint.checkpoint_type == "execution_continuation" and action_claims_missing_support:
            buckets.append("execution_state_support_missing")
        if checkpoint.checkpoint_type == "execution_continuation" and action_events_missing:
            buckets.append("active_action_provenance_missing")
        return JudgeVote(
            judge_id="selected_support_closure_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.FAIL,
            score=0.0,
            confidence=0.9,
            failed_ids=failed,
            failure_buckets=ordered_unique(buckets),
            rationale="selected claims must be directly supported by claim ids and citation events",
        )
    return JudgeVote(
        judge_id="selected_support_closure_judge",
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=JudgeVerdict.PASS,
        score=1.0,
        confidence=0.85,
        covered_ids=output.selected_claim_ids,
        rationale="selected claims have direct supporting claims and citation events",
    )


def _rejection_classification_judge(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> JudgeVote:
    expected_rejected_claims = [
        item for item in checkpoint.expected_excluded_claim_ids if is_visible_claim(scenario, item)
    ]
    expected_rejected_entities = [
        item for item in checkpoint.expected_excluded_entity_ids if is_visible_entity(scenario, item)
    ]
    expected_rejected_entities = ordered_unique(
        [
            *expected_rejected_entities,
            *expected_rejected_claim_subject_entity_ids(scenario, checkpoint),
        ]
    )
    selected_or_supporting = (
        set(output.selected_claim_ids) | set(output.supporting_claim_ids) | set(output.selected_entity_ids)
    )
    bad_selected = [
        item for item in [*expected_rejected_claims, *expected_rejected_entities] if item in selected_or_supporting
    ]
    missing_rejected = [
        item
        for item in expected_rejected_claims
        if item not in output.rejected_claim_ids and item not in output.context_claim_ids
    ] + [
        item
        for item in expected_rejected_entities
        if item not in output.rejected_entity_ids and item not in output.context_entity_ids
    ]
    required_missing = (
        missing_rejected if checkpoint.task_contract.excluded_ids_must_be_rejected_or_contextualized else []
    )
    if bad_selected or required_missing:
        buckets = []
        if bad_selected:
            buckets.append("rejected_id_selected_as_truth")
        if required_missing:
            buckets.append("missing_rejected_id")
        return JudgeVote(
            judge_id="rejection_classification_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.FAIL,
            score=0.0,
            confidence=0.9,
            failed_ids=ordered_unique([*bad_selected, *required_missing]),
            failure_buckets=buckets,
            rationale="excluded ids violated the checkpoint's selection or rejection policy",
        )
    if not expected_rejected_claims and not expected_rejected_entities:
        return JudgeVote(
            judge_id="rejection_classification_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.ABSTAIN,
            score=1.0,
            confidence=0.2,
            failure_buckets=["judge_uncovered_case"],
            rationale="no explicit rejection expectation",
        )
    return JudgeVote(
        judge_id="rejection_classification_judge",
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=JudgeVerdict.PASS,
        score=1.0,
        confidence=0.85,
        covered_ids=[*expected_rejected_claims, *expected_rejected_entities],
        rationale=(
            "excluded ids were rejected or contextualized"
            if checkpoint.task_contract.excluded_ids_must_be_rejected_or_contextualized
            else "excluded ids were not selected as truth"
        ),
    )


def _graph_context_judge(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> JudgeVote:
    if checkpoint.checkpoint_type not in {
        "entity_reconstruction",
        "entity_split_repair",
        "claim_rekey",
        "conflict_audit",
    }:
        return JudgeVote(
            judge_id="graph_context_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.ABSTAIN,
            score=1.0,
            confidence=0.2,
            failure_buckets=["judge_uncovered_case"],
            rationale="no graph context expectation",
        )
    invalid_selected = selected_noncurrent_claim_ids(scenario, checkpoint, output)
    if invalid_selected:
        return JudgeVote(
            judge_id="graph_context_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.FAIL,
            score=0.0,
            confidence=0.9,
            failed_ids=invalid_selected,
            failure_buckets=["graph_context_selected_as_truth"],
            rationale="contextual graph facts were selected as current truth",
        )
    return JudgeVote(
        judge_id="graph_context_judge",
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=JudgeVerdict.PASS,
        score=1.0,
        confidence=0.85,
        rationale="graph context did not pollute selected truth",
    )


def _definition_coverage_judge(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> JudgeVote:
    if (
        checkpoint.task_contract.definition_claim_placement
        != "selected_and_supporting_required"
    ):
        return JudgeVote(
            judge_id="definition_coverage_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.ABSTAIN,
            score=1.0,
            confidence=0.2,
            failure_buckets=["judge_uncovered_case"],
            rationale="definition coverage is not required for this checkpoint",
        )
    required = required_definition_claim_ids_for_selected_claims(scenario, output)
    missing_selected = [claim_id for claim_id in required if claim_id not in output.selected_claim_ids]
    missing_supporting = [claim_id for claim_id in required if claim_id not in output.supporting_claim_ids]
    failed = ordered_unique([*missing_selected, *missing_supporting])
    if failed:
        buckets = ["claim_rekey_error"]
        if missing_supporting:
            buckets.append("missing_provenance")
        return JudgeVote(
            judge_id="definition_coverage_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.FAIL,
            score=0.0,
            confidence=0.9,
            covered_ids=[claim_id for claim_id in required if claim_id in output.selected_claim_ids],
            failed_ids=failed,
            failure_buckets=ordered_unique(buckets),
            rationale="selected graph role claims require selected/supporting entity definition claims",
        )
    return JudgeVote(
        judge_id="definition_coverage_judge",
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=JudgeVerdict.PASS,
        score=1.0,
        confidence=0.9,
        covered_ids=required,
        rationale="selected graph role claims include subject definition coverage",
    )


def _execution_branch_judge(checkpoint: OracleCheckpoint, output: SimSystemOutput) -> JudgeVote:
    if checkpoint.checkpoint_type != "execution_continuation":
        return JudgeVote(
            judge_id="execution_branch_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.ABSTAIN,
            score=1.0,
            confidence=0.2,
            rationale="no execution continuation expectation",
            failure_buckets=["judge_uncovered_case"],
        )
    if output.operation != "next_action" or not output.next_action:
        return JudgeVote(
            judge_id="execution_branch_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.FAIL,
            score=0.0,
            confidence=0.9,
            failed_ids=[checkpoint.checkpoint_id],
            failure_buckets=["abandoned_branch_selected"],
            rationale="execution checkpoint requires operation=next_action and next_action",
        )
    expected_claim_ids = _judge_expected_claim_ids(checkpoint)
    expected_entity_ids = _judge_expected_entity_ids(checkpoint)
    expected_citation_event_ids = _judge_expected_citation_event_ids(checkpoint)
    missing_claims = [claim_id for claim_id in expected_claim_ids if claim_id not in output.selected_claim_ids]
    missing_entities = [entity_id for entity_id in expected_entity_ids if entity_id not in output.selected_entity_ids]
    missing_support = [claim_id for claim_id in expected_claim_ids if claim_id not in output.supporting_claim_ids]
    missing_events = [
        event_id for event_id in expected_citation_event_ids if event_id not in output.supporting_citation_event_ids
    ]
    failed = ordered_unique([*missing_claims, *missing_entities, *missing_support, *missing_events])
    if failed:
        buckets: list[str] = []
        if missing_claims or missing_support:
            buckets.append("execution_state_support_missing")
        if missing_entities:
            buckets.append("execution_state_entity_missing")
        if missing_events:
            buckets.append("active_action_provenance_missing")
        return JudgeVote(
            judge_id="execution_branch_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.FAIL,
            score=0.0,
            confidence=0.9,
            failed_ids=failed,
            failure_buckets=buckets,
            rationale="execution continuation requires selected and supported active continuation state",
        )
    return JudgeVote(
        judge_id="execution_branch_judge",
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=JudgeVerdict.PASS,
        score=1.0,
        confidence=0.9,
        covered_ids=[*expected_claim_ids, *expected_entity_ids, *expected_citation_event_ids],
        rationale="execution continuation selected and supported the active state",
    )
