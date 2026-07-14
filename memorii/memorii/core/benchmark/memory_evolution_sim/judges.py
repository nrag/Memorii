"""Programmatic simulator judges."""

from __future__ import annotations

from memorii.core.benchmark.memory_evolution_sim.judge_features import (
    expected_rejected_claim_subject_entity_ids,
    required_selected_entity_ids_for_policy,
    selected_action_state_event_ids_missing_support,
    selected_claim_evidence_event_ids_missing_support,
    selected_claim_ids_missing_support,
    selected_claim_support_closure_errors,
    supporting_claim_role_violations,
    supporting_rejection_provenance_overlap_ids,
)
from memorii.core.benchmark.memory_evolution_sim.schemas import (
    JudgeAggregate,
    JudgeVerdict,
    JudgeVote,
    LatentGraphScenario,
    ObservabilityLabel,
    OracleCheckpoint,
    SimSystemOutput,
)
from memorii.core.benchmark.memory_evolution_sim.utils import (
    _answer_bucket,
    _bad_supporting_event_ids,
    _claim_bucket,
    _claim_is_bad_support,
    _hidden_answer_leaks,
    _is_visible_claim,
    _is_visible_entity,
    _norm,
    _ordered_unique,
    _relation_bucket,
    _required_definition_claim_ids_for_selected_claims,
    _role_relation_ids,
    _selected_noncurrent_claim_ids,
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
            bucket=_claim_bucket(checkpoint),
        ),
        _set_judge(
            "claim_lifecycle_judge",
            checkpoint,
            expected=expected_claim_ids,
            actual=output.selected_claim_ids,
            bucket=_claim_bucket(checkpoint),
        ),
        _set_judge(
            "temporal_truth_judge",
            checkpoint,
            expected=expected_claim_ids,
            actual=output.selected_claim_ids,
            bucket="historical_truth_lost" if checkpoint.checkpoint_type == "historical_truth" else "wrong_current_truth",
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
            actual=_role_relation_ids(output),
            bucket=_relation_bucket(checkpoint),
        ),
        _set_judge(
            "support_contradiction_judge",
            checkpoint,
            expected=checkpoint.expected_relation_ids,
            actual=_role_relation_ids(output),
            bucket=_relation_bucket(checkpoint),
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
            actual=output.belief_ranking_ids if checkpoint.checkpoint_type == "belief_ranking" else output.claim_ids,
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
        _supporting_evidence_precision_judge(scenario, checkpoint, output),
        _selected_support_closure_judge(scenario, checkpoint, output),
        _rejection_classification_judge(scenario, checkpoint, output),
        _graph_context_judge(scenario, checkpoint, output),
        _definition_coverage_judge(scenario, checkpoint, output),
        _legacy_flattening_judge(checkpoint, output),
        _answer_judge(scenario, checkpoint, output),
        _hidden_hallucination_judge(scenario, checkpoint, output),
        _ambiguity_abstention_judge(checkpoint, output),
        _confidence_calibration_judge(checkpoint, output),
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
        rationale="; ".join(vote.rationale for vote in [*required_failed, *required_abstained, *optional_failed]) or "required judges passed",
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
        "entity_reconstruction": {"entity_type_judge", "alias_resolution_judge", "relation_directionality_judge", "graph_context_judge", "definition_coverage_judge", "selected_truth_precision_judge"},
        "current_truth": {"temporal_truth_judge", "claim_lifecycle_judge", "selected_entity_role_judge", "selected_truth_precision_judge", "supporting_evidence_precision_judge"},
        "historical_truth": {"temporal_truth_judge", "claim_lifecycle_judge", "selected_entity_role_judge", "supporting_evidence_precision_judge"},
        "scoped_truth": {"scope_judge", "selected_entity_role_judge", "selected_truth_precision_judge", "supporting_evidence_precision_judge"},
        "source_trust_conflict": {"source_trust_judge", "support_contradiction_judge", "relation_directionality_judge", "selected_entity_role_judge", "selected_truth_precision_judge", "supporting_evidence_precision_judge"},
        "modality_suppression": {"modality_suppression_judge", "selected_entity_role_judge", "selected_truth_precision_judge", "supporting_evidence_precision_judge"},
        "entity_disambiguation": {"alias_resolution_judge", "selected_entity_role_judge", "selected_truth_precision_judge", "supporting_evidence_precision_judge"},
        "entity_split_repair": {"alias_resolution_judge", "graph_context_judge", "selected_entity_role_judge", "selected_truth_precision_judge", "supporting_evidence_precision_judge"},
        "claim_rekey": {"alias_resolution_judge", "claim_lifecycle_judge", "graph_context_judge", "definition_coverage_judge", "selected_entity_role_judge", "selected_truth_precision_judge"},
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
    if _judge_expected_claim_ids(checkpoint) and checkpoint.checkpoint_contract.supporting_citations_must_be_direct_current_evidence:
        required.add("selected_support_closure_judge")
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
    policy = checkpoint.checkpoint_contract.selected_entity_role_policy
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
    bad_claims = _selected_noncurrent_claim_ids(scenario, checkpoint, output)
    selected_excluded_claims = [item for item in checkpoint.expected_excluded_claim_ids if item in output.selected_claim_ids]
    selected_excluded_entities = [item for item in checkpoint.expected_excluded_entity_ids if item in output.selected_entity_ids]
    selected_rejected_claims = [item for item in output.selected_claim_ids if item in output.rejected_claim_ids]
    failed = _ordered_unique([
        *bad_claims,
        *selected_excluded_claims,
        *selected_excluded_entities,
        *selected_rejected_claims,
    ])
    if failed:
        buckets = ["selected_truth_precision_error"]
        if selected_rejected_claims:
            buckets.append("selected_rejected_channel_overlap")
        return JudgeVote(
            judge_id="selected_truth_precision_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.FAIL,
            score=0.0,
            confidence=0.9,
            failed_ids=failed,
            failure_buckets=_ordered_unique(buckets),
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

def _supporting_evidence_precision_judge(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> JudgeVote:
    excluded_support_claims = [
        item for item in checkpoint.expected_excluded_claim_ids if item in output.supporting_claim_ids
    ]
    bad_claims = [
        item
        for item in [*output.supporting_claim_ids, *output.selected_claim_ids]
        if _claim_is_bad_support(scenario, checkpoint, item)
    ]
    support_role_violations = supporting_claim_role_violations(scenario, checkpoint, output)
    support_role_violation_ids = [
        claim_id
        for claim_ids in support_role_violations.values()
        for claim_id in claim_ids
    ]
    bad_events = _bad_supporting_event_ids(scenario, checkpoint, output.supporting_citation_event_ids)
    supporting_rejected_claims = [item for item in output.supporting_claim_ids if item in output.rejected_claim_ids]
    supporting_rejection_events = supporting_rejection_provenance_overlap_ids(scenario, checkpoint, output)
    failed = _ordered_unique([
        *excluded_support_claims,
        *bad_claims,
        *support_role_violation_ids,
        *bad_events,
        *supporting_rejected_claims,
        *supporting_rejection_events,
    ])
    if failed:
        buckets = []
        if excluded_support_claims:
            buckets.append("supporting_excluded_id")
        if bad_claims:
            buckets.append("supporting_noncurrent_claim_selected")
        if support_role_violation_ids:
            buckets.append("supporting_role_violation")
        if support_role_violations.get("wrong_subject_support"):
            buckets.append("wrong_entity_support_used")
            buckets.append("disambiguation_evidence_used_as_support")
        if bad_events:
            buckets.append("supporting_noisy_or_stale_provenance")
        if supporting_rejected_claims:
            buckets.append("supporting_rejected_channel_overlap")
        if supporting_rejection_events:
            buckets.append("supporting_rejection_provenance_overlap")
        return JudgeVote(
            judge_id="supporting_evidence_precision_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.FAIL,
            score=0.0,
            confidence=0.9,
            failed_ids=failed,
            failure_buckets=buckets,
            rationale=f"supporting channel contains invalid support ids: {failed}",
        )
    return JudgeVote(
        judge_id="supporting_evidence_precision_judge",
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=JudgeVerdict.PASS,
        score=1.0,
        confidence=0.85,
        rationale="supporting channel contains clean answer support",
    )


def _selected_support_closure_judge(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> JudgeVote:
    if not checkpoint.checkpoint_contract.supporting_citations_must_be_direct_current_evidence:
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
        error.claim_id
        for error in closure_errors
        if error.is_action_state and error.missing_supporting_claim
    ]
    action_events_missing = selected_action_state_event_ids_missing_support(closure_errors)
    failed = _ordered_unique([*missing_support_claims, *missing_evidence_event_ids])
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
            failure_buckets=_ordered_unique(buckets),
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
        item
        for item in checkpoint.expected_excluded_claim_ids
        if _is_visible_claim(scenario, item)
    ]
    expected_rejected_entities = [
        item
        for item in checkpoint.expected_excluded_entity_ids
        if _is_visible_entity(scenario, item)
    ]
    expected_rejected_entities = _ordered_unique([
        *expected_rejected_entities,
        *expected_rejected_claim_subject_entity_ids(scenario, checkpoint),
    ])
    selected_or_supporting = set(output.selected_claim_ids) | set(output.supporting_claim_ids) | set(output.selected_entity_ids)
    bad_selected = [item for item in [*expected_rejected_claims, *expected_rejected_entities] if item in selected_or_supporting]
    missing_rejected = [
        item
        for item in expected_rejected_claims
        if item not in output.rejected_claim_ids and item not in output.context_claim_ids
    ] + [
        item
        for item in expected_rejected_entities
        if item not in output.rejected_entity_ids and item not in output.context_entity_ids
    ]
    if bad_selected or missing_rejected:
        buckets = []
        if bad_selected:
            buckets.append("rejected_id_selected_as_truth")
        if missing_rejected:
            buckets.append("missing_rejected_id")
        return JudgeVote(
            judge_id="rejection_classification_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.FAIL,
            score=0.0,
            confidence=0.9,
            failed_ids=_ordered_unique([*bad_selected, *missing_rejected]),
            failure_buckets=buckets,
            rationale="excluded ids must be rejected/contextualized, not selected as truth",
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
        rationale="excluded ids were rejected or contextualized",
    )

def _graph_context_judge(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> JudgeVote:
    if checkpoint.checkpoint_type not in {"entity_reconstruction", "entity_split_repair", "claim_rekey", "conflict_audit"}:
        return JudgeVote(
            judge_id="graph_context_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.ABSTAIN,
            score=1.0,
            confidence=0.2,
            failure_buckets=["judge_uncovered_case"],
            rationale="no graph context expectation",
        )
    invalid_selected = _selected_noncurrent_claim_ids(scenario, checkpoint, output)
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
    if not checkpoint.checkpoint_contract.definition_claims_required_in_selected:
        return JudgeVote(
            judge_id="definition_coverage_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.ABSTAIN,
            score=1.0,
            confidence=0.2,
            failure_buckets=["judge_uncovered_case"],
            rationale="definition coverage is not required for this checkpoint",
        )
    required = _required_definition_claim_ids_for_selected_claims(scenario, output)
    missing_selected = [claim_id for claim_id in required if claim_id not in output.selected_claim_ids]
    missing_supporting = [claim_id for claim_id in required if claim_id not in output.supporting_claim_ids]
    failed = _ordered_unique([*missing_selected, *missing_supporting])
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
            failure_buckets=_ordered_unique(buckets),
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

def _legacy_flattening_judge(checkpoint: OracleCheckpoint, output: SimSystemOutput) -> JudgeVote:
    expected_claims = set(output.selected_claim_ids) | set(output.supporting_claim_ids) | set(output.context_claim_ids) | set(output.rejected_claim_ids)
    expected_entities = set(output.selected_entity_ids) | set(output.context_entity_ids) | set(output.rejected_entity_ids)
    expected_relations = set(output.selected_relation_ids) | set(output.supporting_relation_ids) | set(output.context_relation_ids) | set(output.rejected_relation_ids)
    expected_events = set(output.supporting_citation_event_ids) | set(output.context_citation_event_ids) | set(output.rejection_citation_event_ids)
    mismatches = []
    if not expected_claims.issubset(set(output.claim_ids)):
        mismatches.append("claim_ids")
    if not expected_entities.issubset(set(output.entity_ids)):
        mismatches.append("entity_ids")
    if not expected_relations.issubset(set(output.relation_ids)):
        mismatches.append("relation_ids")
    if not expected_events.issubset(set(output.citation_event_ids)):
        mismatches.append("citation_event_ids")
    if mismatches:
        return JudgeVote(
            judge_id="legacy_flattening_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.PASS,
            score=0.8,
            confidence=0.8,
            failed_ids=mismatches,
            failure_buckets=["legacy_flattening_mismatch"],
            rationale=f"legacy fields were normalized from role-aware views: {mismatches}",
        )
    return JudgeVote(
        judge_id="legacy_flattening_judge",
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=JudgeVerdict.PASS,
        score=1.0,
        confidence=0.7,
        rationale="legacy flattened fields include role-aware views",
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
    failed = _ordered_unique([*missing_claims, *missing_entities, *missing_support, *missing_events])
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

def _answer_judge(scenario: LatentGraphScenario, checkpoint: OracleCheckpoint, output: SimSystemOutput) -> JudgeVote:
    if not checkpoint.checkpoint_contract.answer_required:
        return JudgeVote(
            judge_id="answer_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.PASS,
            score=1.0,
            confidence=0.7,
            failure_buckets=["graph_answer_optional_missing"] if not output.answer and checkpoint.expected_answer else [],
            rationale="answer text is diagnostic for this checkpoint; structured graph/action state is authoritative",
        )
    if checkpoint.expected_abstention:
        verdict = JudgeVerdict.PASS if output.answer in {None, "unknown"} or output.uncertain_ids else JudgeVerdict.FAIL
        return JudgeVote(
            judge_id="ambiguity_answer_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=verdict,
            score=1.0 if verdict == JudgeVerdict.PASS else 0.0,
            confidence=0.8,
            failed_ids=[] if verdict == JudgeVerdict.PASS else checkpoint.expected_uncertain_ids,
            failure_buckets=[] if verdict == JudgeVerdict.PASS else ["ambiguous_fact_overcommitted"],
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
        failure_buckets=[] if passed else [_answer_bucket(checkpoint)],
        rationale="answer matched" if passed else f"answer {actual!r} did not match {expected!r}",
    )

def _answer_matches_expected(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    actual: str,
    expected: str,
) -> bool:
    actual_norm = _norm(actual)
    expected_norm = _norm(expected)
    if expected_norm in actual_norm or actual_norm in expected_norm:
        return True
    expected_entity_ids = set(checkpoint.expected_entity_ids)
    for entity in scenario.entities:
        if entity.entity_id not in expected_entity_ids:
            continue
        names = {entity.canonical_name, *[alias.alias_text for alias in entity.aliases]}
        if any(_norm(name) and _norm(name) in actual_norm for name in names):
            return True
    return False

def _hidden_hallucination_judge(
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
    asserted = (
        set(output.entity_ids)
        | set(output.selected_entity_ids)
        | set(output.rejected_entity_ids)
        | set(output.context_entity_ids)
        | set(output.claim_ids)
        | set(output.selected_claim_ids)
        | set(output.supporting_claim_ids)
        | set(output.rejected_claim_ids)
        | set(output.context_claim_ids)
        | set(output.relation_ids)
        | set(output.selected_relation_ids)
        | set(output.supporting_relation_ids)
        | set(output.rejected_relation_ids)
        | set(output.context_relation_ids)
    )
    hallucinated = sorted(asserted & hidden_ids)
    answer_leaks = _hidden_answer_leaks(scenario, output)
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

def _ambiguity_abstention_judge(checkpoint: OracleCheckpoint, output: SimSystemOutput) -> JudgeVote:
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
        item for item in checkpoint.expected_uncertain_ids
        if item in output.entity_ids or item in output.claim_ids or item in output.relation_ids
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

def _confidence_calibration_judge(checkpoint: OracleCheckpoint, output: SimSystemOutput) -> JudgeVote:
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
