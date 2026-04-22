"""Typed benchmark fixtures, observations, and report models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.domain.enums import CommitStatus, MemoryDomain, TemporalValidityStatus
from memorii.domain.retrieval import RetrievalIntent, RetrievalScope
from memorii.domain.routing import InboundEvent


class BenchmarkScenarioType(str, Enum):
    TRANSCRIPT_RETRIEVAL = "transcript_retrieval"
    SEMANTIC_RETRIEVAL = "semantic_retrieval"
    EPISODIC_RETRIEVAL = "episodic_retrieval"
    ROUTING_CORRECTNESS = "routing_correctness"
    EXECUTION_RESUME = "execution_resume"
    SOLVER_RESUME = "solver_resume"
    SOLVER_VALIDATION = "solver_validation"
    END_TO_END = "end_to_end"
    LEARNING_ACROSS_EPISODES = "learning_across_episodes"
    LONG_HORIZON_DEGRADATION = "long_horizon_degradation"
    CONFLICT_RESOLUTION = "conflict_resolution"
    IMPLICIT_RECALL = "implicit_recall"


class BenchmarkSystem(str, Enum):
    MEMORII = "memorii"
    TRANSCRIPT_ONLY_BASELINE = "transcript_only_baseline"
    FLAT_RETRIEVAL_BASELINE = "flat_retrieval_baseline"
    NO_SOLVER_GRAPH_BASELINE = "no_solver_graph_baseline"


class ScenarioExecutionLevel(str, Enum):
    SYSTEM_LEVEL = "system_level"
    COMPONENT_LEVEL = "component_level"


class BaselinePolicy(str, Enum):
    RUN = "run"
    SKIP = "skip"


class BaselineApplicability(BaseModel):
    policy: BaselinePolicy = BaselinePolicy.RUN
    skip_reason: str | None = None

    model_config = ConfigDict(extra="forbid")


class RetrievalFixtureMemoryItem(BaseModel):
    item_id: str
    domain: MemoryDomain
    text: str
    task_id: str | None = None
    execution_node_id: str | None = None
    solver_run_id: str | None = None
    status: CommitStatus = CommitStatus.COMMITTED
    validity_status: TemporalValidityStatus = TemporalValidityStatus.ACTIVE
    valid_from: datetime | None = None
    valid_to: datetime | None = None

    model_config = ConfigDict(extra="forbid")


class RetrievalFixture(BaseModel):
    query: str
    intent: RetrievalIntent
    scope: RetrievalScope
    top_k: int = 3
    corpus: list[RetrievalFixtureMemoryItem] = Field(default_factory=list)
    expected_relevant_ids: list[str] = Field(default_factory=list)
    expected_excluded_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class RoutingFixture(BaseModel):
    inbound_event: InboundEvent
    expected_domains: list[MemoryDomain] = Field(default_factory=list)
    expected_blocked_domains: list[MemoryDomain] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class ExecutionResumeFixture(BaseModel):
    task_id: str
    expected_node_ids: list[str] = Field(default_factory=list)
    expected_status_by_node: dict[str, str] = Field(default_factory=dict)
    include_blocked_node: bool = True

    model_config = ConfigDict(extra="forbid")


class SolverResumeFixture(BaseModel):
    solver_run_id: str
    execution_node_id: str
    expected_frontier: list[str] = Field(default_factory=list)
    expected_unresolved_questions: list[str] = Field(default_factory=list)
    expected_reopenable_branches: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class SolverValidationFixture(BaseModel):
    decision: str
    evidence_ids: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    next_best_test: str | None = None
    available_evidence_ids: set[str] = Field(default_factory=set)
    expect_downgrade: bool = False
    expect_invalid_rejection: bool = False
    expect_abstention_preserved: bool = False

    model_config = ConfigDict(extra="forbid")


class EndToEndFixture(BaseModel):
    task_id: str
    expect_pipeline_success: bool = True
    expect_writeback_domains: list[MemoryDomain] = Field(default_factory=list)
    expect_writeback_candidate_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class LearningAcrossEpisodesFixture(BaseModel):
    episode_two_query: str
    top_k: int = 3
    corpus: list[RetrievalFixtureMemoryItem] = Field(default_factory=list)
    expected_reuse_id: str
    baseline_without_reuse_retrieved_ids: list[str] = Field(default_factory=list)
    episode_one_writeback_domains: list[MemoryDomain] = Field(default_factory=list)
    expected_writeback_domain: MemoryDomain
    expected_writeback_domains: list[MemoryDomain] = Field(default_factory=list)
    expected_writeback_candidate_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate_expected_writeback(self) -> "LearningAcrossEpisodesFixture":
        if not self.expected_writeback_domains:
            self.expected_writeback_domains = [self.expected_writeback_domain]
        return self


class LongHorizonDegradationFixture(BaseModel):
    early_retrieval: RetrievalFixture
    delayed_retrieval: RetrievalFixture
    noise_ids: list[str] = Field(default_factory=list)
    delayed_depends_on_early_context: bool = True

    model_config = ConfigDict(extra="forbid")


class ConflictCandidate(BaseModel):
    candidate_id: str
    recency_rank: int
    validity_status: str
    preferred: bool = False
    timestamp: datetime | None = None
    version: int | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate_temporal_semantics(self) -> "ConflictCandidate":
        has_timestamp_or_version = self.timestamp is not None or self.version is not None
        has_validity_window = self.valid_from is not None or self.valid_to is not None
        if not has_timestamp_or_version and not has_validity_window:
            raise ValueError(
                "conflict candidate must include timestamp/version or explicit validity window"
            )
        return self


class ConflictResolutionFixture(BaseModel):
    candidates: list[ConflictCandidate] = Field(default_factory=list)
    expected_winner_candidate_id: str

    model_config = ConfigDict(extra="forbid")


class ImplicitRecallFixture(BaseModel):
    query: str
    context_tokens: list[str] = Field(default_factory=list)
    top_k: int = 3
    corpus: list[RetrievalFixtureMemoryItem] = Field(default_factory=list)
    relevant_ids: list[str] = Field(default_factory=list)
    relevant_memory_texts: list[str] = Field(default_factory=list)
    lexical_overlap_score: float
    max_lexical_overlap: float = 0.25
    expected_domains: list[MemoryDomain] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate_lexical_overlap(self) -> "ImplicitRecallFixture":
        if self.lexical_overlap_score > self.max_lexical_overlap:
            raise ValueError(
                f"implicit recall lexical overlap {self.lexical_overlap_score} exceeds "
                f"maximum {self.max_lexical_overlap}"
            )
        if not self.relevant_memory_texts:
            raise ValueError("implicit recall fixture requires relevant_memory_texts")
        return self


class BenchmarkScenarioFixture(BaseModel):
    scenario_id: str
    category: BenchmarkScenarioType
    retrieval: RetrievalFixture | None = None
    routing: RoutingFixture | None = None
    execution_resume: ExecutionResumeFixture | None = None
    solver_resume: SolverResumeFixture | None = None
    solver_validation: SolverValidationFixture | None = None
    end_to_end: EndToEndFixture | None = None
    learning_across_episodes: LearningAcrossEpisodesFixture | None = None
    long_horizon_degradation: LongHorizonDegradationFixture | None = None
    conflict_resolution: ConflictResolutionFixture | None = None
    implicit_recall: ImplicitRecallFixture | None = None
    baseline_applicability: dict[BenchmarkSystem, BaselineApplicability] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate_category_fixture_contract(self) -> "BenchmarkScenarioFixture":
        fixture_fields = {
            "retrieval": self.retrieval is not None,
            "routing": self.routing is not None,
            "execution_resume": self.execution_resume is not None,
            "solver_resume": self.solver_resume is not None,
            "solver_validation": self.solver_validation is not None,
            "end_to_end": self.end_to_end is not None,
            "learning_across_episodes": self.learning_across_episodes is not None,
            "long_horizon_degradation": self.long_horizon_degradation is not None,
            "conflict_resolution": self.conflict_resolution is not None,
            "implicit_recall": self.implicit_recall is not None,
        }
        expected_field_by_category = {
            BenchmarkScenarioType.TRANSCRIPT_RETRIEVAL: "retrieval",
            BenchmarkScenarioType.SEMANTIC_RETRIEVAL: "retrieval",
            BenchmarkScenarioType.EPISODIC_RETRIEVAL: "retrieval",
            BenchmarkScenarioType.ROUTING_CORRECTNESS: "routing",
            BenchmarkScenarioType.EXECUTION_RESUME: "execution_resume",
            BenchmarkScenarioType.SOLVER_RESUME: "solver_resume",
            BenchmarkScenarioType.SOLVER_VALIDATION: "solver_validation",
            BenchmarkScenarioType.END_TO_END: "end_to_end",
            BenchmarkScenarioType.LEARNING_ACROSS_EPISODES: "learning_across_episodes",
            BenchmarkScenarioType.LONG_HORIZON_DEGRADATION: "long_horizon_degradation",
            BenchmarkScenarioType.CONFLICT_RESOLUTION: "conflict_resolution",
            BenchmarkScenarioType.IMPLICIT_RECALL: "implicit_recall",
        }
        expected_field = expected_field_by_category[self.category]
        active_fields = [name for name, is_set in fixture_fields.items() if is_set]
        if expected_field not in active_fields:
            raise ValueError(f"{self.category.value} requires {expected_field} fixture data")
        invalid_fields = [name for name in active_fields if name != expected_field and name != "routing"]
        if self.category == BenchmarkScenarioType.END_TO_END:
            invalid_fields = [
                name for name in active_fields if name not in {"end_to_end", "routing", "retrieval"}
            ]
        else:
            invalid_fields = [name for name in active_fields if name != expected_field]
        if invalid_fields:
            raise ValueError(
                f"{self.category.value} received invalid fixture subtype(s): {', '.join(sorted(invalid_fields))}"
            )
        return self


class ScenarioObservation(BaseModel):
    scenario_id: str
    category: BenchmarkScenarioType
    system: BenchmarkSystem
    execution_level: ScenarioExecutionLevel = ScenarioExecutionLevel.COMPONENT_LEVEL
    retrieved_ids: list[str] = Field(default_factory=list)
    relevant_ids: list[str] = Field(default_factory=list)
    excluded_ids: list[str] = Field(default_factory=list)
    retrieval_latency_ms: float = 0.0
    routed_domains: list[MemoryDomain] = Field(default_factory=list)
    blocked_domains: list[MemoryDomain] = Field(default_factory=list)
    expected_routed_domains: list[MemoryDomain] = Field(default_factory=list)
    expected_blocked_domains: list[MemoryDomain] = Field(default_factory=list)
    runtime_observability_status: str | None = None
    runtime_observability_missing: list[str] = Field(default_factory=list)
    execution_resume_correct: bool | None = None
    solver_resume_correct: bool | None = None
    frontier_restore_correct: bool | None = None
    unresolved_restore_correct: bool | None = None
    downgraded: bool | None = None
    abstention_preserved: bool | None = None
    invalid_output_rejected: bool | None = None
    scenario_success: bool | None = None
    writeback_candidate_domains: list[MemoryDomain] = Field(default_factory=list)
    expected_writeback_candidate_domains: list[MemoryDomain] = Field(default_factory=list)
    writeback_candidate_ids: list[str] = Field(default_factory=list)
    expected_writeback_candidate_ids: list[str] = Field(default_factory=list)
    semantic_pollution: bool | None = None
    user_memory_pollution: bool | None = None
    cross_episode_reuse_correct: bool | None = None
    baseline_without_reuse_success: bool | None = None
    writeback_reuse_correct: bool | None = None
    performance_improvement_over_baseline: float | None = None
    early_recall: float | None = None
    delayed_recall: float | None = None
    early_latency_ms: float | None = None
    delayed_latency_ms: float | None = None
    noise_hit_count: int | None = None
    retrieval_recall_degradation: float | None = None
    retrieval_latency_growth: float | None = None
    resume_correctness_under_scale: bool | None = None
    noise_resilience: float | None = None
    conflict_detected: bool | None = None
    conflict_resolution_correct: bool | None = None
    stale_memory_rejected: bool | None = None
    contradictory_handling_correct: bool | None = None
    implicit_recall_success: bool | None = None
    retrieval_plan_relevance_accuracy: bool | None = None
    false_positive_retrieval_rate: float | None = None

    model_config = ConfigDict(extra="forbid")


class ScenarioMetrics(BaseModel):
    recall_at_k: float | None = None
    precision_at_k: float | None = None
    retrieval_latency_ms: float | None = None
    routing_accuracy: float | None = None
    blocked_write_accuracy: float | None = None
    multi_domain_fanout_correctness: float | None = None
    execution_resume_correctness: float | None = None
    solver_resume_correctness: float | None = None
    frontier_restore_correctness: float | None = None
    unresolved_restore_correctness: float | None = None
    unsupported_commitment_downgrade_rate: float | None = None
    abstention_preservation_rate: float | None = None
    invalid_output_rejection_rate: float | None = None
    scenario_success_rate: float | None = None
    writeback_candidate_correctness: float | None = None
    semantic_pollution_rate: float | None = None
    user_memory_pollution_rate: float | None = None
    cross_episode_reuse_accuracy: float | None = None
    performance_improvement_over_baseline: float | None = None
    writeback_reuse_correctness: float | None = None
    retrieval_recall_degradation: float | None = None
    retrieval_latency_growth: float | None = None
    resume_correctness_under_scale: float | None = None
    noise_resilience: float | None = None
    conflict_detection_rate: float | None = None
    correct_preference_for_newer_or_valid_memory: float | None = None
    stale_memory_rejection_rate: float | None = None
    contradictory_memory_handling_correctness: float | None = None
    implicit_recall_success_rate: float | None = None
    retrieval_plan_relevance_accuracy: float | None = None
    false_positive_retrieval_rate: float | None = None

    model_config = ConfigDict(extra="forbid")


class ScenarioResult(BaseModel):
    scenario_id: str
    category: BenchmarkScenarioType
    system: BenchmarkSystem
    observation: ScenarioObservation
    metrics: ScenarioMetrics

    model_config = ConfigDict(extra="forbid")


class BaselineDelta(BaseModel):
    baseline: BenchmarkSystem
    metric_deltas: dict[str, float] = Field(default_factory=dict)
    skipped: bool = False
    skip_reason: str | None = None

    model_config = ConfigDict(extra="forbid")


class BenchmarkRunConfig(BaseModel):
    seed: int = 7
    run_label: str = "benchmark"
    run_reproducibility_check: bool = False

    model_config = ConfigDict(extra="forbid")


class BenchmarkRunReport(BaseModel):
    run_id: str
    generated_at: datetime
    config: BenchmarkRunConfig
    scenario_results: list[ScenarioResult] = Field(default_factory=list)
    aggregate_by_system: dict[BenchmarkSystem, ScenarioMetrics] = Field(default_factory=dict)
    aggregate_by_category: dict[BenchmarkScenarioType, dict[BenchmarkSystem, ScenarioMetrics]] = Field(default_factory=dict)
    baseline_comparison: dict[str, list[BaselineDelta]] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class BenchmarkEnvironmentInfo(BaseModel):
    python_version: str
    platform: str
    architecture: str | None = None

    model_config = ConfigDict(extra="forbid")


class BenchmarkReportMetadata(BaseModel):
    run_id: str
    timestamp: datetime
    git_commit: str | None = None
    memorii_version: str | None = None
    environment: BenchmarkEnvironmentInfo

    model_config = ConfigDict(extra="forbid")


class CanonicalBenchmarkConfig(BaseModel):
    dataset: str | None = None
    fixture_source: str | None = None
    subset_size: int | None = None
    seed: int
    benchmark_categories: list[BenchmarkScenarioType] = Field(default_factory=list)
    systems: list[BenchmarkSystem] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class CanonicalBenchmarkSummary(BaseModel):
    total_scenarios: int
    passed: int
    failed: int
    aggregate_metrics: dict[str, dict[str, float | None]] = Field(default_factory=dict)
    baseline_comparison_summary: dict[str, dict[str, float | None]] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class CanonicalBenchmarkCategoryEntry(BaseModel):
    category: BenchmarkScenarioType
    scenario_count: int
    metrics: dict[str, dict[str, float | None]] = Field(default_factory=dict)
    baseline_delta: dict[str, dict[str, float | None]] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class CanonicalScenarioTrace(BaseModel):
    routing_result: dict[str, object] | None = None
    retrieval_plan: dict[str, object] | None = None
    retrieved_ids: list[str] = Field(default_factory=list)
    solver_decision: dict[str, object] | None = None
    verifier_result: dict[str, object] | None = None
    writeback_candidates: dict[str, object] | None = None

    model_config = ConfigDict(extra="forbid")


class CanonicalScenarioEntry(BaseModel):
    scenario_id: str
    category: BenchmarkScenarioType
    system: BenchmarkSystem
    execution_type: ScenarioExecutionLevel
    passed: bool
    metrics: dict[str, float | None] = Field(default_factory=dict)
    expected: dict[str, object] = Field(default_factory=dict)
    observed: dict[str, object] = Field(default_factory=dict)
    trace: CanonicalScenarioTrace
    error: str | None = None
    notes: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class CanonicalBaselineEntry(BaseModel):
    aggregate_metrics: dict[str, float | None] = Field(default_factory=dict)
    deltas_vs_memorii: dict[str, float | None] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class CanonicalBenchmarkReport(BaseModel):
    metadata: BenchmarkReportMetadata
    config: CanonicalBenchmarkConfig
    summary: CanonicalBenchmarkSummary
    categories: list[CanonicalBenchmarkCategoryEntry] = Field(default_factory=list)
    scenarios: list[CanonicalScenarioEntry] = Field(default_factory=list)
    baselines: dict[BenchmarkSystem, CanonicalBaselineEntry] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
