"""Typed calibration telemetry models."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class CalibrationItemType(str, Enum):
    SOURCE_OBSERVATION = "source_observation"
    ENTITY = "entity"
    CLAIM = "claim"
    RELATION = "relation"
    ACTION = "action"
    GRAPH_NODE = "graph_node"
    GRAPH_EDGE = "graph_edge"
    ANSWER = "answer"


class CalibrationHierarchyLayer(str, Enum):
    OBSERVATION = "observation"
    EXTRACTION = "extraction"
    VALIDATION = "validation"
    EVOLUTION = "evolution"
    GRAPH = "graph"
    RETRIEVAL_DECISION = "retrieval_decision"


class CalibrationDecisionChannel(str, Enum):
    SELECTED = "selected"
    SUPPORTING = "supporting"
    REJECTED = "rejected"
    CONTEXT = "context"
    ABSTAINED = "abstained"


class CalibrationLabel(str, Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class CalibrationLabelSource(str, Enum):
    LATENT_ORACLE = "latent_oracle"
    PROGRAMMATIC_JUDGE = "programmatic_judge"
    HUMAN_REVIEW = "human_review"
    RUNTIME_UNKNOWN = "runtime_unknown"


class CalibrationResponseLevel(str, Enum):
    REPORT_ONLY = "report_only"
    REVIEW = "review"
    CONFIDENCE_CAP = "confidence_cap"
    ABSTAIN_THRESHOLD = "abstain_threshold"
    BENCHMARK_FAIL = "benchmark_fail"


class DecisionAction(str, Enum):
    ANSWER_CURRENT_TRUTH = "answer_current_truth"
    ANSWER_HISTORICAL_TRUTH = "answer_historical_truth"
    SELECT_SUPPORT = "select_support"
    REJECT_STALE_FACT = "reject_stale_fact"
    EXPOSE_CONFLICT = "expose_conflict"
    ABSTAIN = "abstain"
    CONTINUE_EXECUTION_BRANCH = "continue_execution_branch"
    RECONSTRUCT_GRAPH = "reconstruct_graph"


class CalibrationLabelRecord(BaseModel):
    label: CalibrationLabel
    label_source: CalibrationLabelSource
    label_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    label_rationale: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(extra="forbid")


class CalibrationEvent(BaseModel):
    event_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    suite: str
    scenario_id: str
    checkpoint_id: str
    item_id: str
    item_type: CalibrationItemType
    hierarchy_layer: CalibrationHierarchyLayer
    decision_channel: CalibrationDecisionChannel
    confidence: float = Field(ge=0.0, le=1.0)
    label: CalibrationLabel
    label_source: CalibrationLabelSource
    label_sources: list[CalibrationLabelSource] = Field(default_factory=list)
    label_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    label_rationale: str
    label_history: list[CalibrationLabelRecord] = Field(default_factory=list)
    failure_buckets: list[str] = Field(default_factory=list)
    source_modality: str | None = None
    source_trust: int | None = None
    predicate_id: str | None = None
    scope_key: str | None = None
    lifecycle_state: str | None = None
    retrieval_view: str | None = None
    entity_ambiguity: str | None = None
    evidence_event_ids: list[str] = Field(default_factory=list)
    judge_ids: list[str] = Field(default_factory=list)
    decision_action: DecisionAction | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    def model_post_init(self, __context: object) -> None:
        if not self.label_sources:
            self.label_sources.append(self.label_source)
        if not self.label_history:
            self.label_history.append(
                CalibrationLabelRecord(
                    label=self.label,
                    label_source=self.label_source,
                    label_confidence=self.label_confidence,
                    label_rationale=self.label_rationale,
                )
            )


class CalibrationSlice(BaseModel):
    slice_key: str
    slice_values: dict[str, str]
    n: int = Field(ge=0)
    accuracy: float | None = None
    mean_confidence: float | None = None
    ece: float | None = None
    brier_score: float | None = None
    wilson_low: float | None = None
    wilson_high: float | None = None
    eligible_for_failure: bool = False
    response_level: CalibrationResponseLevel = CalibrationResponseLevel.REPORT_ONLY

    model_config = ConfigDict(extra="forbid")


class CalibrationReport(BaseModel):
    event_count: int = Field(ge=0)
    labeled_event_count: int = Field(ge=0)
    overall_accuracy: float | None = None
    ece: float | None = None
    brier_score: float | None = None
    overconfident_wrong_count: int = Field(default=0, ge=0)
    low_confidence_correct_count: int = Field(default=0, ge=0)
    hidden_hallucination_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    ambiguous_overcommit_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    worst_slices: list[CalibrationSlice] = Field(default_factory=list)
    rolling_windows: dict[str, object] = Field(default_factory=dict)
    response_recommendations: dict[str, int] = Field(default_factory=dict)
    label_source_counts: dict[str, int] = Field(default_factory=dict)
    hierarchy_layer_counts: dict[str, int] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class DecisionCostReport(BaseModel):
    decision_cost_total: float
    decision_cost_mean: float
    cost_by_failure_bucket: dict[str, float] = Field(default_factory=dict)
    cost_by_checkpoint_type: dict[str, float] = Field(default_factory=dict)
    cost_by_source_modality: dict[str, float] = Field(default_factory=dict)
    cost_by_decision_action: dict[str, float] = Field(default_factory=dict)
    regret_total: float = 0.0
    regret_mean: float = 0.0

    model_config = ConfigDict(extra="forbid")
