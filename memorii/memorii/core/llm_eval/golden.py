"""Curated offline golden snapshots for LLM decision evals."""

from __future__ import annotations

from datetime import UTC, datetime

from memorii.core.llm_decision.models import EvalSnapshot, LLMDecisionPoint
from memorii.core.promotion.models import PromotionCandidateType

_GOLDEN_CREATED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def _promotion_snapshot(
    *,
    snapshot_id: str,
    candidate_id: str,
    candidate_type: PromotionCandidateType,
    content: str,
    created_from: str,
    expected_output: dict[str, object],
    tags: list[str],
    repeated_across_episodes: int = 0,
    explicit_user_memory_request: bool = False,
    related_memory_ids: list[str] | None = None,
) -> EvalSnapshot:
    return EvalSnapshot(
        snapshot_id=snapshot_id,
        decision_point=LLMDecisionPoint.PROMOTION,
        input_payload={
            "candidate_id": candidate_id,
            "candidate_type": candidate_type.value,
            "content": content,
            "created_from": created_from,
            "repeated_across_episodes": repeated_across_episodes,
            "explicit_user_memory_request": explicit_user_memory_request,
            "related_memory_ids": related_memory_ids or [],
        },
        expected_output=expected_output,
        source="offline_golden",
        tags=tags,
        created_at=_GOLDEN_CREATED_AT,
    )


def promotion_golden_v1() -> list[EvalSnapshot]:
    """Return curated v1 promotion snapshots for deterministic offline evals."""
    return [
        _promotion_snapshot(
            snapshot_id="promotion:v1:explicit-user-preference",
            candidate_id="cand:user:concise-direct",
            candidate_type=PromotionCandidateType.USER_MEMORY,
            content="Remember that I prefer concise direct answers.",
            created_from="explicit_memory_request",
            explicit_user_memory_request=True,
            expected_output={
                "promote": True,
                "target_plane": "user_memory",
                "min_confidence": 0.8,
                "rationale_contains": "explicit_user_memory_request",
            },
            tags=[
                "domain:personal_assistant",
                "task_type:interaction_style",
                "memory_class:user_memory",
            ],
        ),
        _promotion_snapshot(
            snapshot_id="promotion:v1:inferred-repeated-preference",
            candidate_id="cand:user:concise-pattern",
            candidate_type=PromotionCandidateType.USER_MEMORY,
            content="Across several chats, user repeatedly asks for concise output.",
            created_from="observation",
            repeated_across_episodes=4,
            expected_output={"requires_judge_review": True},
            tags=[
                "domain:personal_assistant",
                "task_type:interaction_style",
                "memory_class:user_memory",
            ],
        ),
        _promotion_snapshot(
            snapshot_id="promotion:v1:one-off-trip-preference",
            candidate_id="cand:user:iceland-hotel-base",
            candidate_type=PromotionCandidateType.USER_MEMORY,
            content="For this Iceland trip, prefer one hotel base.",
            created_from="observation",
            repeated_across_episodes=1,
            expected_output={
                "promote": False,
                "max_confidence": 0.5,
                "rationale_contains": "observation_not_promoted",
            },
            tags=[
                "domain:travel_planning",
                "task_type:temporary_planning_preference",
                "memory_class:user_memory",
            ],
        ),
        _promotion_snapshot(
            snapshot_id="promotion:v1:noisy-observation-tests-passed",
            candidate_id="cand:episode:tests-passed-question",
            candidate_type=PromotionCandidateType.EPISODIC,
            content="User asked whether tests passed.",
            created_from="observation",
            expected_output={
                "promote": False,
                "max_confidence": 0.5,
                "rationale_contains": "observation_not_promoted",
            },
            tags=[
                "domain:software_engineering",
                "task_type:implementation",
                "memory_class:episodic",
            ],
        ),
        _promotion_snapshot(
            snapshot_id="promotion:v1:task-outcome-jsonl-store",
            candidate_id="cand:episode:jsonl-latest-wins",
            candidate_type=PromotionCandidateType.EPISODIC,
            content="Implemented JSONL memory plane store with latest-wins replay.",
            created_from="task_outcome",
            expected_output={
                "promote": True,
                "target_plane": "episodic",
                "min_confidence": 0.7,
                "rationale_contains": "task_outcome",
            },
            tags=[
                "domain:software_engineering",
                "task_type:implementation",
                "memory_class:episodic",
            ],
        ),
        _promotion_snapshot(
            snapshot_id="promotion:v1:investigation-conclusion-refresh-token",
            candidate_id="cand:incident:oauth-refresh-expired",
            candidate_type=PromotionCandidateType.EPISODIC,
            content="Login failures were caused by expired OAuth refresh tokens.",
            created_from="investigation_conclusion",
            expected_output={
                "promote": True,
                "target_plane": "episodic",
                "min_confidence": 0.7,
                "rationale_contains": "investigation_conclusion",
            },
            tags=[
                "domain:debugging_incident_investigation",
                "task_type:root_cause_analysis",
                "memory_class:episodic",
            ],
        ),
        _promotion_snapshot(
            snapshot_id="promotion:v1:decision-finalized-qdrant",
            candidate_id="cand:decision:qdrant-vs-weaviate",
            candidate_type=PromotionCandidateType.EPISODIC,
            content="Use Qdrant over Weaviate due to latency and operational simplicity.",
            created_from="decision_finalized",
            expected_output={
                "promote": True,
                "target_plane": "episodic",
                "min_confidence": 0.7,
                "rationale_contains": "decision_finalized",
            },
            tags=[
                "domain:decision_making_architecture",
                "task_type:decision_making",
                "memory_class:episodic",
            ],
        ),
        _promotion_snapshot(
            snapshot_id="promotion:v1:semantic-jsonl-repeated",
            candidate_id="cand:semantic:jsonl-append-replay",
            candidate_type=PromotionCandidateType.SEMANTIC,
            content="Memorii uses append/replay JSONL stores for inspectable persistence.",
            created_from="observation",
            repeated_across_episodes=3,
            expected_output={
                "promote": True,
                "target_plane": "semantic",
                "min_confidence": 0.6,
                "rationale_contains": "repeated_across_episodes",
            },
            tags=[
                "domain:software_engineering",
                "task_type:system_design",
                "memory_class:semantic",
            ],
        ),
        _promotion_snapshot(
            snapshot_id="promotion:v1:project-fact-locomo-parked",
            candidate_id="cand:project:locomo-parked",
            candidate_type=PromotionCandidateType.PROJECT_FACT,
            content="LoCoMo is parked until synthetic state-engine benchmarks pass.",
            created_from="observation",
            repeated_across_episodes=3,
            expected_output={
                "promote": True,
                "target_plane": "project_fact",
                "min_confidence": 0.6,
                "rationale_contains": "repeated_across_episodes",
            },
            tags=[
                "domain:product_project_management",
                "task_type:project_planning",
                "memory_class:project_fact",
            ],
        ),
        _promotion_snapshot(
            snapshot_id="promotion:v1:user-memory-single-observation-tables",
            candidate_id="cand:user:prefers-tables",
            candidate_type=PromotionCandidateType.USER_MEMORY,
            content="User prefers tables.",
            created_from="observation",
            repeated_across_episodes=1,
            expected_output={
                "promote": False,
                "max_confidence": 0.5,
                "rationale_contains": "observation_not_promoted",
            },
            tags=[
                "domain:personal_assistant",
                "task_type:preference_inference",
                "memory_class:user_memory",
            ],
        ),
        _promotion_snapshot(
            snapshot_id="promotion:v1:customer-security-review-repeated",
            candidate_id="cand:project:customer-security-review",
            candidate_type=PromotionCandidateType.PROJECT_FACT,
            content="Customer ACME requires security review before each rollout.",
            created_from="observation",
            repeated_across_episodes=4,
            expected_output={
                "promote": True,
                "target_plane": "project_fact",
                "min_confidence": 0.6,
                "rationale_contains": "repeated_across_episodes",
            },
            tags=[
                "domain:customer_support_operations",
                "task_type:customer_follow_up",
                "memory_class:project_fact",
            ],
        ),
        _promotion_snapshot(
            snapshot_id="promotion:v1:research-conclusion-blf",
            candidate_id="cand:research:blf-belief-updates",
            candidate_type=PromotionCandidateType.EPISODIC,
            content=(
                "Literature review concluded BLF-style belief updates help separate "
                "support, refutation, and uncertainty."
            ),
            created_from="task_outcome",
            expected_output={
                "promote": True,
                "target_plane": "episodic",
                "min_confidence": 0.7,
                "rationale_contains": "task_outcome",
            },
            tags=[
                "domain:research_analysis",
                "task_type:literature_review",
                "memory_class:episodic",
            ],
        ),
        _promotion_snapshot(
            snapshot_id="promotion:v1:planning-one-off-locomo-next-week",
            candidate_id="cand:project:locomo-next-week",
            candidate_type=PromotionCandidateType.PROJECT_FACT,
            content="Let's prioritize LoCoMo next week.",
            created_from="observation",
            repeated_across_episodes=1,
            expected_output={
                "promote": False,
                "max_confidence": 0.5,
                "rationale_contains": "observation_not_promoted",
            },
            tags=[
                "domain:product_project_management",
                "task_type:planning",
                "memory_class:project_fact",
            ],
        ),
        _promotion_snapshot(
            snapshot_id="promotion:v1:duplicate-merge-placeholder",
            candidate_id="cand:semantic:jsonl-persistence-duplicate",
            candidate_type=PromotionCandidateType.SEMANTIC,
            content="Restates the JSONL append/replay persistence project fact.",
            created_from="observation",
            repeated_across_episodes=3,
            related_memory_ids=["mem:semantic:jsonl-persistence"],
            expected_output={
                "promote": True,
                "target_plane": "semantic",
                "requires_judge_review": True,
            },
            tags=[
                "domain:software_engineering",
                "task_type:memory_maintenance",
                "memory_class:semantic",
            ],
        ),
    ]
