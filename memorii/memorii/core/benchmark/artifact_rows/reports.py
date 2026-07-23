"""Typed benchmark summaries, manifests, and top-level report contracts."""

from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import Field, field_validator, model_validator

from memorii.core.benchmark.artifact_rows.checkpoints import (
    RuntimeCheckpointResultRow,
    SimCheckpointResultRow,
)
from memorii.core.benchmark.artifact_rows.common import (
    ArtifactJsonObject,
    BenchmarkSuiteName,
    CountMap,
    DecisionMode,
    FinalOutputSource,
    FlatArtifactModel,
    ProviderHealthStatus,
    empty_json_object,
    execution_source_from_counts,
)
from memorii.core.benchmark.calibration.models import CalibrationReport, DecisionCostReport
from memorii.core.benchmark.memory_evolution_sim.schemas import SimSystemOutput
from memorii.core.benchmark.reproducibility import SourceState, canonical_json_digest
from memorii.core.llm_decision.models import LLMDecisionTrace
from memorii.core.memory_evolution.models import (
    ExtractionFailureCode,
    ExtractionRunStatus,
    FallbackOutcome,
    ProviderAttemptStatus,
)
from memorii.core.memory_evolution.models import (
    FinalExtractionSource as MemoryFinalExtractionSource,
)

_CALIBRATION_REQUIRED_SUITES = {"memory_evolution_sim_v1", "memory_evolution_runtime_v1"}


class RuntimeGraphSummary(FlatArtifactModel):
    """Stable summary contract for runtime graph completeness metrics."""

    source_observation_count: int = Field(ge=0)
    entity_count: int = Field(ge=0)
    claim_count: int = Field(ge=0)
    action_count: int = Field(ge=0)
    relation_item_count: int = Field(ge=0)
    action_item_count: int = Field(ge=0)
    graph_edge_count: int = Field(ge=0)
    graph_edge_counts_by_type: CountMap = Field(default_factory=dict)
    runtime_graph_node_counts_by_type: CountMap = Field(default_factory=dict)
    runtime_graph_item_counts_by_type: CountMap = Field(default_factory=dict)
    runtime_relation_support_modes: CountMap = Field(default_factory=dict)
    evidence_edge_count: int = Field(ge=0)
    active_claim_count: int = Field(ge=0)
    active_claim_with_subject_count: int = Field(ge=0)
    active_claim_with_object_or_literal_count: int = Field(ge=0)
    active_claim_with_scope_count: int = Field(ge=0)
    active_claim_with_observed_in_count: int = Field(ge=0)
    active_action_count: int = Field(ge=0)
    active_action_with_observed_in_count: int = Field(ge=0)
    active_claim_with_subject_rate: float = Field(ge=0.0, le=1.0)
    active_claim_with_object_or_literal_rate: float = Field(ge=0.0, le=1.0)
    active_claim_with_scope_rate: float = Field(ge=0.0, le=1.0)
    active_claim_with_observed_in_rate: float = Field(ge=0.0, le=1.0)
    active_action_with_observed_in_rate: float = Field(ge=0.0, le=1.0)
    runtime_graph_validation_error_count: int = Field(ge=0)
    snapshot_count: int = Field(default=0, ge=0)
    aggregation_scope: Literal["final_snapshot_per_scenario"] = "final_snapshot_per_scenario"
    cumulative_graph_edge_count: int = Field(default=0, ge=0)
    cumulative_validation_error_count: int = Field(default=0, ge=0)
    terminal_snapshot_count: int = Field(default=0, ge=0)
    terminal_snapshot_anomaly_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_derived_graph_metrics(self) -> RuntimeGraphSummary:
        if sum(self.graph_edge_counts_by_type.values()) != self.graph_edge_count:
            raise ValueError("graph edge counts by type must sum to graph_edge_count")
        node_counts = self.runtime_graph_node_counts_by_type
        for item_type, count in (
            ("entity", self.entity_count),
            ("claim", self.claim_count),
            ("action", self.action_count),
        ):
            if node_counts.get(item_type, 0) != count:
                raise ValueError(f"{item_type}_count must match runtime graph node counts")
        item_counts = self.runtime_graph_item_counts_by_type
        if item_counts.get("relation", 0) != self.relation_item_count:
            raise ValueError("relation_item_count must match runtime graph item counts")
        if item_counts.get("action", 0) != self.action_item_count:
            raise ValueError("action_item_count must match runtime graph item counts")
        coverage = (
            (self.active_claim_with_subject_count, self.active_claim_with_subject_rate),
            (
                self.active_claim_with_object_or_literal_count,
                self.active_claim_with_object_or_literal_rate,
            ),
            (self.active_claim_with_scope_count, self.active_claim_with_scope_rate),
            (self.active_claim_with_observed_in_count, self.active_claim_with_observed_in_rate),
        )
        for count, rate in coverage:
            if count > self.active_claim_count:
                raise ValueError("active claim edge coverage cannot exceed active_claim_count")
            expected_rate = count / max(1, self.active_claim_count)
            if abs(rate - expected_rate) > 1e-12:
                raise ValueError("active claim edge coverage rate disagrees with its count")
        if self.active_action_with_observed_in_count > self.active_action_count:
            raise ValueError("active action edge coverage cannot exceed active_action_count")
        expected_action_rate = self.active_action_with_observed_in_count / max(1, self.active_action_count)
        if abs(self.active_action_with_observed_in_rate - expected_action_rate) > 1e-12:
            raise ValueError("active action edge coverage rate disagrees with its count")
        return self


class RuntimeProviderHealth(FlatArtifactModel):
    """Typed provider-health gate for runtime-backed benchmark runs."""

    effective_decision_mode: DecisionMode | None = None
    attempted_calls: int = Field(ge=0)
    provider_successes: int = Field(ge=0)
    provider_failures: int = Field(ge=0)
    fallbacks: int = Field(ge=0)
    provider_success_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    status: ProviderHealthStatus
    clean_runtime_gate: bool
    failure_buckets: list[str] = Field(default_factory=list)
    failure_classification_counts: CountMap = Field(default_factory=dict)
    provider_attempt_status_counts: CountMap = Field(default_factory=dict)
    extraction_status_counts: CountMap = Field(default_factory=dict)
    fallback_outcome_counts: CountMap = Field(default_factory=dict)
    output_validation_failures: int = Field(default=0, ge=0)
    abstentions: int = Field(default=0, ge=0)
    partial_extractions: int = Field(default=0, ge=0)
    execution_source: FinalOutputSource
    dry_run: bool
    fake_extractor_calls: int = Field(default=0, ge=0)
    provider_metadata: dict[str, str] = Field(default_factory=dict)
    policy: dict[str, str]

    @model_validator(mode="after")
    def validate_provider_accounting(self) -> RuntimeProviderHealth:
        if self.attempted_calls != self.provider_successes + self.provider_failures:
            raise ValueError("attempted provider calls must equal successes plus failures")
        if sum(self.provider_attempt_status_counts.values()) < self.attempted_calls:
            raise ValueError("provider status counts cannot underreport attempted calls")
        if self.dry_run:
            if any((self.attempted_calls, self.provider_successes, self.provider_failures, self.fallbacks)):
                raise ValueError("dry runtime health cannot contain provider accounting")
            if self.execution_source == "live_llm":
                raise ValueError("dry runtime health cannot claim live execution")
        elif self.fake_extractor_calls or self.execution_source == "fake_oracle":
            raise ValueError("live runtime health cannot contain fake provenance")
        if self.status == "not_applicable":
            if self.provider_success_rate is not None:
                raise ValueError("not-applicable provider health cannot report a success rate")
            if not self.clean_runtime_gate:
                raise ValueError("not-applicable provider health must not fail the runtime gate")
            return self
        expected_rate = self.provider_successes / self.attempted_calls if self.attempted_calls else 0.0
        if self.provider_success_rate is None or abs(self.provider_success_rate - expected_rate) > 1e-12:
            raise ValueError("provider success rate disagrees with provider call counts")
        expected_clean = self.status == "pass"
        if self.clean_runtime_gate != expected_clean:
            raise ValueError("clean_runtime_gate must agree with provider health status")
        return self


class AlignmentSummary(FlatArtifactModel):
    """Stable summary contract for runtime graph alignment artifacts."""

    alignment_summary_policy: dict[str, str]
    checkpoint_expected_alignment_audit_count: int = Field(ge=0)
    checkpoint_expected_alignment_audit_counts: CountMap = Field(default_factory=dict)
    checkpoint_expected_alignment_audit_counts_by_item_type: CountMap = Field(default_factory=dict)
    checkpoint_scored_verdict_counts: CountMap = Field(default_factory=dict)
    checkpoint_scored_review_required_count: int = Field(ge=0)
    checkpoint_scored_failure_bucket_counts: CountMap = Field(default_factory=dict)
    full_graph_audit_alignment_count: int = Field(ge=0)
    full_graph_audit_alignment_counts: CountMap = Field(default_factory=dict)
    full_graph_audit_alignment_counts_by_item_type: CountMap = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_alignment_totals(self) -> AlignmentSummary:
        if sum(self.checkpoint_expected_alignment_audit_counts.values()) != (
            self.checkpoint_expected_alignment_audit_count
        ):
            raise ValueError("checkpoint alignment verdict counts must sum to checkpoint alignment count")
        if sum(self.checkpoint_expected_alignment_audit_counts_by_item_type.values()) != (
            self.checkpoint_expected_alignment_audit_count
        ):
            raise ValueError("checkpoint alignment item counts must sum to checkpoint alignment count")
        if sum(self.full_graph_audit_alignment_counts.values()) != self.full_graph_audit_alignment_count:
            raise ValueError("full graph alignment verdict counts must sum to full graph alignment count")
        if sum(self.full_graph_audit_alignment_counts_by_item_type.values()) != self.full_graph_audit_alignment_count:
            raise ValueError("full graph alignment item counts must sum to full graph alignment count")
        return self


class RuntimeReportSummary(FlatArtifactModel):
    """Typed runtime-only report section; no free-form duplicate metrics."""

    runtime_checkpoint_count: int = Field(ge=0)
    runtime_failure_bucket_counts: CountMap = Field(default_factory=dict)
    provider_successes: int = Field(ge=0)
    provider_failures: int = Field(ge=0)
    fallbacks: int = Field(ge=0)
    final_output_source_counts: CountMap = Field(default_factory=dict)
    runtime_alignment_count: int = Field(ge=0)
    runtime_graph_item_count: int = Field(ge=0)
    runtime_graph_item_observation_count: int = Field(ge=0)
    runtime_graph_summary: RuntimeGraphSummary
    runtime_graph_alignments_summary: AlignmentSummary
    long_horizon_slice_counts: ArtifactJsonObject = Field(default_factory=empty_json_object)
    runtime_provider_health: RuntimeProviderHealth

    @model_validator(mode="after")
    def validate_runtime_summary(self) -> RuntimeReportSummary:
        if sum(self.final_output_source_counts.values()) != self.runtime_checkpoint_count:
            raise ValueError("runtime output source counts must sum to runtime checkpoint count")
        if self.runtime_provider_health.execution_source != execution_source_from_counts(
            self.final_output_source_counts
        ):
            raise ValueError("runtime provider health source must match checkpoint source counts")
        if self.runtime_alignment_count != self.runtime_graph_alignments_summary.full_graph_audit_alignment_count:
            raise ValueError("runtime alignment count must match full graph alignment count")
        if self.runtime_graph_item_count != sum(self.runtime_graph_summary.runtime_graph_item_counts_by_type.values()):
            raise ValueError("runtime graph item count must match graph summary item counts")
        health = self.runtime_provider_health
        if self.provider_successes != health.provider_successes:
            raise ValueError("runtime provider_successes must match provider health")
        if self.provider_failures != health.provider_failures:
            raise ValueError("runtime provider_failures must match provider health")
        if self.fallbacks != health.fallbacks:
            raise ValueError("runtime fallbacks must match provider health")
        return self


class WarningExampleRow(FlatArtifactModel):
    """Stable row contract for warning-only examples."""

    scenario_id: str
    checkpoint_id: str
    checkpoint_type: str
    warning_bucket: str
    warning_buckets: list[str]
    reason: str
    context_claim_ids: list[str] = Field(default_factory=list)
    context_entity_ids: list[str] = Field(default_factory=list)
    context_relation_ids: list[str] = Field(default_factory=list)
    context_citation_event_ids: list[str] = Field(default_factory=list)
    covered_ids: list[str] = Field(default_factory=list)
    failed_ids: list[str] = Field(default_factory=list)
    selected_claim_ids: list[str] = Field(default_factory=list)
    selected_entity_ids: list[str] = Field(default_factory=list)


class WarningPolicyEntry(FlatArtifactModel):
    level: Literal["warning_only", "failure", "informational"]
    rationale: str = ""


class ValidationScenarioCatalogRow(FlatArtifactModel):
    scenario_id: str
    semantic_world_fingerprint: str = Field(min_length=16)
    family: str
    profile: str
    observation_count: int = Field(ge=0)
    checkpoint_count: int = Field(ge=0)
    checkpoint_types: list[str] = Field(default_factory=list)
    difficulty_tags: list[str] = Field(default_factory=list)
    phase_counts: CountMap = Field(default_factory=dict)
    max_horizon_distance: int = Field(ge=0)
    max_interference_count: int = Field(ge=0)
    hidden_item_count: int = Field(ge=0)
    observed_claim_count: int = Field(ge=0)
    inferable_claim_count: int = Field(ge=0)


class SimScenarioResultRow(FlatArtifactModel):
    scenario_id: str
    semantic_world_fingerprint: str = Field(min_length=16)
    family: str
    profile: str
    decision_mode: DecisionMode
    effective_decision_mode: DecisionMode
    checkpoint_count: int = Field(ge=0)
    success: bool
    failure_mode: str | None = None
    checkpoints_passed: int = Field(ge=0)
    checkpoints_failed: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_checkpoint_accounting(self) -> SimScenarioResultRow:
        if self.checkpoints_passed + self.checkpoints_failed != self.checkpoint_count:
            raise ValueError("scenario checkpoint outcomes must sum to checkpoint_count")
        if self.success != (self.checkpoints_failed == 0):
            raise ValueError("scenario success must agree with checkpoint outcomes")
        if self.success and self.failure_mode is not None:
            raise ValueError("successful scenarios cannot report a failure_mode")
        if not self.success and not self.failure_mode:
            raise ValueError("failed scenarios require a failure_mode")
        return self


class SimLLMTraceRow(FlatArtifactModel):
    """Typed simulator decision trace retained until JSONL serialization."""

    scenario_id: str
    checkpoint_id: str
    transition_type: Literal["memory_evolution_sim_reconstruction"]
    decision_mode: DecisionMode
    effective_decision_mode: DecisionMode
    final_output_source: FinalOutputSource
    trace: LLMDecisionTrace
    success: bool
    fallback_used: bool
    failure_mode: str | None = None
    output: SimSystemOutput

    @model_validator(mode="after")
    def validate_outcome(self) -> SimLLMTraceRow:
        if self.success and (self.fallback_used or self.failure_mode is not None):
            raise ValueError("successful LLM traces cannot report fallback or failure")
        if self.fallback_used and not self.failure_mode:
            raise ValueError("fallback traces require a failure_mode")
        return self


class RuntimeExtractorTracePayload(FlatArtifactModel):
    """Auditable, secret-free metadata for one runtime extraction call."""

    provider: str
    model: str | None = None
    prompt_hash: str | None = None
    scenario_id: str
    call_index: int = Field(ge=0)
    input_source_ids: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    entity_count: int = Field(ge=0)
    claim_count: int = Field(ge=0)
    action_count: int = Field(ge=0)
    validation_summary: CountMap = Field(default_factory=dict)


class RuntimeExtractorOutput(FlatArtifactModel):
    entity_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    action_ids: list[str] = Field(default_factory=list)


class RuntimeExtractorTraceRow(FlatArtifactModel):
    """Typed runtime extractor trace retained until JSONL serialization."""

    scenario_id: str
    checkpoint_id: str | None = None
    transition_type: Literal["runtime_memory_extraction"]
    decision_mode: DecisionMode
    effective_decision_mode: DecisionMode
    final_output_source: FinalOutputSource
    trace: RuntimeExtractorTracePayload
    extraction_status: ExtractionRunStatus
    provider_attempt_status: ProviderAttemptStatus
    fallback_outcome: FallbackOutcome
    final_extraction_source: MemoryFinalExtractionSource
    failure_code: ExtractionFailureCode | None = None
    primary_failure_code: ExtractionFailureCode | None = None
    fallback_provider: str | None = None
    output: RuntimeExtractorOutput

    @model_validator(mode="after")
    def validate_outcome(self) -> RuntimeExtractorTraceRow:
        if self.extraction_status == ExtractionRunStatus.SUCCEEDED and self.failure_code is not None:
            raise ValueError("successful extractor trace cannot report a terminal failure")
        if self.extraction_status == ExtractionRunStatus.FAILED and self.failure_code is None:
            raise ValueError("failed extractor trace requires a failure code")
        fallback_used = self.fallback_outcome != FallbackOutcome.NOT_USED
        if fallback_used != bool(self.fallback_provider):
            raise ValueError("fallback outcome and provider provenance disagree")
        if self.fallback_outcome == FallbackOutcome.SUCCEEDED:
            if self.final_extraction_source != MemoryFinalExtractionSource.FALLBACK:
                raise ValueError("successful fallback must identify fallback output")
        elif self.final_extraction_source == MemoryFinalExtractionSource.FALLBACK:
            raise ValueError("fallback output requires a successful fallback")
        return self


class ArtifactManifestEntry(FlatArtifactModel):
    """Digest and size for one persisted run artifact."""

    relative_path: str = Field(min_length=1)
    media_type: Literal["application/json", "application/jsonl", "text/markdown"]
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        if value != value.strip() or value.startswith("/") or ".." in value.split("/"):
            raise ValueError("artifact manifest paths must be normalized relative paths")
        return value


class ArtifactManifest(FlatArtifactModel):
    """Canonical inventory bound into a benchmark report."""

    run_id: str = Field(min_length=1)
    source_revision: str = Field(min_length=1)
    source_tree_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_state: SourceState
    entries: list[ArtifactManifestEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_entries(self) -> ArtifactManifest:
        paths = [entry.relative_path for entry in self.entries]
        if paths != sorted(set(paths)):
            raise ValueError("artifact manifest paths must be unique and sorted")
        return self

    def digest(self) -> str:
        return canonical_json_digest(self.model_dump(mode="json"))


class BenchmarkReportSummary(FlatArtifactModel):
    """Minimum stable report contract shared by benchmark report.json files."""

    suite: BenchmarkSuiteName
    mode: DecisionMode
    profile: str
    seed: int
    benchmark_key: str = ""
    fixture_fingerprint: str = Field(min_length=1)
    evaluation_fingerprint: str = Field(min_length=1)
    system_fingerprint: str = Field(min_length=1)
    source_revision: str = Field(min_length=1)
    source_tree_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_state: SourceState
    report_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    inference_replicate: int = Field(default=0, ge=0)
    run_id: str = ""
    generated_at: str = ""
    fixture_source: str = ""
    fixture_hashes: dict[str, str] = Field(default_factory=dict)
    scenario_count: int = Field(ge=0)
    validation_scenario_catalog: list[ValidationScenarioCatalogRow] = Field(default_factory=list)
    event_count: int = Field(ge=0)
    checkpoint_count: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    llm_calls: int = Field(ge=0)
    provider_successes: int = Field(ge=0)
    provider_failures: int = Field(ge=0)
    fallbacks: int = Field(ge=0)
    fake_calls: int = Field(default=0, ge=0)
    dry_run: bool = False
    execution_source: FinalOutputSource = "mixed"
    final_output_source_counts: CountMap = Field(default_factory=dict)
    metrics: ArtifactJsonObject = Field(default_factory=empty_json_object)
    long_horizon_slice_counts: ArtifactJsonObject = Field(default_factory=empty_json_object)
    calibration: CalibrationReport | ArtifactJsonObject = Field(default_factory=empty_json_object)
    decision_quality: DecisionCostReport | ArtifactJsonObject = Field(default_factory=empty_json_object)
    failure_bucket_counts: CountMap = Field(default_factory=dict)
    critical_failure_bucket_counts: CountMap = Field(default_factory=dict)
    warning_bucket_counts: CountMap = Field(default_factory=dict)
    review_bucket_counts: CountMap = Field(default_factory=dict)
    judge_metrics: ArtifactJsonObject = Field(default_factory=empty_json_object)
    baseline_scores: ArtifactJsonObject = Field(default_factory=empty_json_object)
    artifact_version: int = Field(default=1, ge=1)
    scenario_results: list[SimScenarioResultRow] = Field(default_factory=list)
    # The simulator row is the strict base shape; runtime-only fields are
    # required for runtime rows and therefore make the second union branch
    # win only when those fields are present.
    checkpoint_results: list[SimCheckpointResultRow | RuntimeCheckpointResultRow] = Field(default_factory=list)
    runtime: RuntimeReportSummary | None = None
    runtime_graph_summary: RuntimeGraphSummary | None = None
    runtime_graph_alignments_summary: AlignmentSummary | None = None
    runtime_failure_bucket_counts: CountMap = Field(default_factory=dict)
    runtime_provider_health: RuntimeProviderHealth | None = None
    warning_policy: dict[str, WarningPolicyEntry] = Field(default_factory=dict)
    hidden_item_count: int | None = Field(default=None, ge=0)
    hidden_hallucination_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    hidden_answer_leak_rate: float | None = Field(default=None, ge=0.0, le=1.0)

    def computed_content_digest(self) -> str:
        payload = self.model_dump(mode="json")
        payload.pop("report_content_digest", None)
        return canonical_json_digest(payload)

    def with_content_digest(self) -> BenchmarkReportSummary:
        return self.model_copy(update={"report_content_digest": self.computed_content_digest()})

    def has_valid_content_digest(self) -> bool:
        return self.report_content_digest == self.computed_content_digest()

    @model_validator(mode="after")
    def validate_nested_report_sections(self) -> BenchmarkReportSummary:
        if self.passed + self.failed != self.scenario_count:
            raise ValueError("passed and failed counts must sum to scenario_count")
        if self.scenario_results:
            if len(self.scenario_results) != self.scenario_count:
                raise ValueError("scenario result rows must match scenario_count")
            scenario_passed = sum(1 for row in self.scenario_results if row.success)
            if scenario_passed != self.passed:
                raise ValueError("scenario result successes must match passed")
        if self.checkpoint_results and len(self.checkpoint_results) != self.checkpoint_count:
            raise ValueError("checkpoint result rows must match checkpoint_count")
        if self.checkpoint_results:
            row_source_counts = Counter(row.final_output_source for row in self.checkpoint_results)
            if dict(sorted(row_source_counts.items())) != dict(
                sorted(self.final_output_source_counts.items())
            ):
                raise ValueError("checkpoint output sources must match top-level source counts")
        if self.dry_run and any((self.provider_successes, self.provider_failures, self.fallbacks)):
            raise ValueError("dry-run reports cannot contain provider successes, failures, or fallbacks")
        source_names = {source for source, count in self.final_output_source_counts.items() if count}
        if self.dry_run and "live_llm" in source_names:
            raise ValueError("dry-run reports cannot contain live LLM output")
        if not self.dry_run and ("fake_oracle" in source_names or self.fake_calls):
            raise ValueError("live reports cannot contain fake execution provenance")
        if self.execution_source != execution_source_from_counts(self.final_output_source_counts):
            raise ValueError("execution_source must be derived from final_output_source_counts")
        calibration_required = self.suite in _CALIBRATION_REQUIRED_SUITES
        runtime_required = self.suite == "memory_evolution_runtime_v1"
        runtime_sections = (
            self.runtime,
            self.runtime_graph_summary,
            self.runtime_graph_alignments_summary,
            self.runtime_provider_health,
        )
        if runtime_required and any(section is None for section in runtime_sections):
            raise ValueError("runtime reports require all typed runtime report sections")
        if not runtime_required and any(section is not None for section in runtime_sections):
            raise ValueError("non-runtime reports cannot contain runtime report sections")
        if isinstance(self.calibration, ArtifactJsonObject) and self.calibration.root:
            self.calibration = CalibrationReport.model_validate(self.calibration.root)
        elif calibration_required and isinstance(self.calibration, ArtifactJsonObject):
            raise ValueError(f"{self.suite} report requires calibration")
        if isinstance(self.decision_quality, ArtifactJsonObject) and self.decision_quality.root:
            self.decision_quality = DecisionCostReport.model_validate(self.decision_quality.root)
        elif calibration_required and isinstance(self.decision_quality, ArtifactJsonObject):
            raise ValueError(f"{self.suite} report requires decision_quality")
        if self.final_output_source_counts and sum(self.final_output_source_counts.values()) != self.checkpoint_count:
            raise ValueError("final output source counts must sum to checkpoint_count")
        undocumented_warning_buckets = set(self.warning_bucket_counts) - set(self.warning_policy)
        if undocumented_warning_buckets:
            raise ValueError(
                f"warning bucket counts require explicit warning policy entries: {sorted(undocumented_warning_buckets)}"
            )
        if self.runtime_provider_health is not None:
            health = self.runtime_provider_health
            if health.provider_successes != self.provider_successes:
                raise ValueError("top-level and runtime provider success counts disagree")
            if health.provider_failures != self.provider_failures:
                raise ValueError("top-level and runtime provider failure counts disagree")
            if health.fallbacks != self.fallbacks:
                raise ValueError("top-level and runtime fallback counts disagree")
        if self.runtime_graph_alignments_summary is not None:
            scored = self.runtime_graph_alignments_summary.checkpoint_scored_verdict_counts
            if scored and sum(scored.values()) != self.checkpoint_count:
                raise ValueError("scored checkpoint verdict counts must sum to checkpoint_count")
        if self.runtime is not None:
            if self.runtime.runtime_checkpoint_count != self.checkpoint_count:
                raise ValueError("runtime checkpoint count must match top-level checkpoint_count")
            if self.runtime.runtime_graph_summary != self.runtime_graph_summary:
                raise ValueError("nested and top-level runtime graph summaries disagree")
            if self.runtime.runtime_graph_alignments_summary != self.runtime_graph_alignments_summary:
                raise ValueError("nested and top-level runtime alignment summaries disagree")
            if self.runtime.runtime_provider_health != self.runtime_provider_health:
                raise ValueError("nested and top-level runtime provider health summaries disagree")
            if self.runtime.provider_successes != self.provider_successes:
                raise ValueError("nested and top-level provider success counts disagree")
            if self.runtime.provider_failures != self.provider_failures:
                raise ValueError("nested and top-level provider failure counts disagree")
            if self.runtime.fallbacks != self.fallbacks:
                raise ValueError("nested and top-level fallback counts disagree")
            if self.runtime.final_output_source_counts != self.final_output_source_counts:
                raise ValueError("nested and top-level output source counts disagree")
            if self.runtime.runtime_failure_bucket_counts != self.runtime_failure_bucket_counts:
                raise ValueError("nested and top-level runtime failure buckets disagree")
            if self.runtime.long_horizon_slice_counts != self.long_horizon_slice_counts:
                raise ValueError("nested and top-level long-horizon slice counts disagree")
        return self
