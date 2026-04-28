from memorii.core.llm_judge.judges import (
    AttributionJudge,
    BeliefDirectionJudge,
    MemoryPlaneJudge,
    PromotionPrecisionJudge,
    TemporalValidityJudge,
)
from memorii.core.llm_judge.jury import JuryAggregator


def test_wave1_judges_aggregate_and_disagreement_behavior() -> None:
    promotion_context = {
        "candidate_id": "cand:wave1",
        "candidate_type": "project_fact",
        "content": "Current workaround for now this sprint",
        "source_ids": ["src:1"],
        "related_memory_ids": [],
        "repeated_across_episodes": 3,
        "explicit_user_memory_request": False,
        "created_from": "observation",
        "metadata": {"source_actor": "tool", "source_kind": "tool", "asserted_by": "tool"},
    }
    belief_payload = {
        "context": {
            "prior_belief": 0.4,
            "decision": "SUPPORTED",
            "evidence_count": 2,
            "missing_evidence_count": 0,
            "verifier_downgraded": False,
            "conflict_count": 0,
            "evidence_ids": ["ev:1"],
            "missing_evidence": [],
            "metadata": {},
        },
        "actual_output": {"belief": 0.8},
    }

    verdicts = [
        PromotionPrecisionJudge().judge(input_payload=promotion_context),
        TemporalValidityJudge().judge(input_payload=promotion_context),
        AttributionJudge().judge(input_payload=promotion_context),
        MemoryPlaneJudge().judge(input_payload={"context": promotion_context, "actual_output": {"target_plane": "semantic"}}),
        BeliefDirectionJudge().judge(input_payload=belief_payload),
    ]

    jury = JuryAggregator().aggregate(verdicts=verdicts, snapshot_id="snap:wave1")
    assert len(jury.dimensions) == 5
    assert jury.disagreement is True
    assert jury.needs_human_review is True
