"""Supporting-evidence precision judges for simulator checkpoints."""

from __future__ import annotations

from memorii.core.benchmark.memory_evolution_sim.judge_features import (
    rejected_required_definition_claim_ids,
    supporting_claim_role_violations,
    supporting_rejection_provenance_overlap_ids,
)
from memorii.core.benchmark.memory_evolution_sim.schemas import (
    JudgeVerdict,
    JudgeVote,
    LatentGraphScenario,
    OracleCheckpoint,
    SimSystemOutput,
)
from memorii.core.benchmark.memory_evolution_sim.utils import (
    bad_supporting_event_ids,
    claim_is_bad_support,
    ordered_unique,
)


def judge_supporting_evidence_precision(
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
        if claim_is_bad_support(scenario, checkpoint, item)
    ]
    support_role_violations = supporting_claim_role_violations(scenario, checkpoint, output)
    support_role_violation_ids = [claim_id for claim_ids in support_role_violations.values() for claim_id in claim_ids]
    bad_events = bad_supporting_event_ids(scenario, checkpoint, output.supporting_citation_event_ids)
    supporting_rejected_claims = [item for item in output.supporting_claim_ids if item in output.rejected_claim_ids]
    rejected_definition_claims = rejected_required_definition_claim_ids(scenario, output)
    supporting_rejection_events = supporting_rejection_provenance_overlap_ids(
        scenario,
        checkpoint,
        output,
    )
    failed = ordered_unique(
        [
            *excluded_support_claims,
            *bad_claims,
            *support_role_violation_ids,
            *bad_events,
            *supporting_rejected_claims,
            *rejected_definition_claims,
            *supporting_rejection_events,
        ]
    )
    if failed:
        buckets = []
        if excluded_support_claims:
            buckets.append("supporting_excluded_id")
        if bad_claims:
            buckets.append("supporting_noncurrent_claim_selected")
        if support_role_violation_ids:
            buckets.append("supporting_role_violation")
        if support_role_violations.get("wrong_subject_support"):
            buckets.extend(("wrong_entity_support_used", "disambiguation_evidence_used_as_support"))
        if support_role_violations.get("execution_context_support"):
            buckets.append("execution_context_claim_used_as_support")
        if bad_events:
            buckets.append("supporting_noisy_or_stale_provenance")
        if supporting_rejected_claims:
            buckets.append("supporting_rejected_channel_overlap")
        if rejected_definition_claims:
            buckets.append("definition_claim_rejected")
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
