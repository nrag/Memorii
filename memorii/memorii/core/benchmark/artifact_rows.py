"""Typed benchmark artifact contracts.

The benchmark artifacts intentionally remain flat JSON for existing readers.
Internally, however, rows are validated through strict models. Suite-specific
or legacy fields live in ``legacy_fields`` and are flattened only at the final
JSON boundary.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.calibration.models import CalibrationReport, DecisionCostReport

_CALIBRATION_REQUIRED_SUITES = {"memory_evolution_sim_v1", "memory_evolution_runtime_v1"}

BenchmarkSuiteName: TypeAlias = Literal["memory_evolution_sim_v1", "memory_evolution_runtime_v1"]
DecisionMode: TypeAlias = Literal["auto", "rule", "llm", "hybrid"]
CheckpointVerdict: TypeAlias = Literal["pass", "fail", "abstain"]
AlignmentVerdict: TypeAlias = Literal[
    "aligned",
    "partial",
    "missing_expected",
    "unmatched_runtime",
    "ambiguous_alignment",
]
FinalOutputSource: TypeAlias = Literal["rule", "fake_oracle", "live_llm", "llm"]
ProviderCountScope: TypeAlias = Literal["scenario_extractor_calls"]
ActionSupportMode: TypeAlias = Literal[
    "runtime_action_item_exact",
    "runtime_action_semantic",
    "runtime_action_work_state_bridge",
    "claim_derived_action",
    "partial_action",
    "missing_action",
    "ambiguous_action",
    "ambiguous_work_state_bridge",
]
AlignmentItemType: TypeAlias = Literal["entity", "claim", "relation", "action", "evidence"]


class FlatArtifactModel(BaseModel):
    """Strict artifact model with a controlled flat-JSON compatibility escape."""

    legacy_fields: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def from_flat_row(cls, row: dict[str, object]) -> FlatArtifactModel:
        model_fields = set(cls.model_fields) - {"legacy_fields"}
        payload = {key: value for key, value in row.items() if key in model_fields}
        payload["legacy_fields"] = {key: value for key, value in row.items() if key not in model_fields}
        return cls.model_validate(payload)

    def to_json_row(self) -> dict[str, object]:
        payload = {
            field_name: _artifact_value_to_json(getattr(self, field_name))
            for field_name in type(self).model_fields
            if field_name != "legacy_fields"
        }
        collisions = set(payload) & set(self.legacy_fields)
        if collisions:
            raise ValueError(f"legacy artifact fields cannot overwrite typed fields: {sorted(collisions)}")
        payload.update(_artifact_value_to_json(self.legacy_fields))
        return payload


def artifact_row_to_json(row: FlatArtifactModel) -> dict[str, object]:
    """Serialize a validated artifact row at an explicit JSON boundary."""

    return row.to_json_row()


def artifact_rows_to_json(rows: Sequence[FlatArtifactModel]) -> list[dict[str, object]]:
    """Serialize artifact rows at explicit JSON/report boundaries."""

    return [artifact_row_to_json(row) for row in rows]


def artifact_section_legacy_fields(
    row_model: type[FlatArtifactModel],
    *sections: BaseModel | dict[str, Any],
) -> dict[str, Any]:
    """Flatten typed sections while excluding fields owned by ``row_model``.

    Checkpoint artifacts intentionally keep a flat JSON shape. Builders should
    compose typed sections first, then use this helper to preserve legacy flat
    fields without risking collisions with first-class row fields.
    """

    typed_fields = set(row_model.model_fields) - {"legacy_fields"}
    flattened: dict[str, Any] = {}
    for section in sections:
        section_fields = section.model_dump(mode="json") if isinstance(section, BaseModel) else section
        flattened.update({key: value for key, value in section_fields.items() if key not in typed_fields})
    return flattened


def _artifact_value_to_json(value: Any) -> Any:
    if isinstance(value, FlatArtifactModel):
        return value.to_json_row()
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_artifact_value_to_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _artifact_value_to_json(item) for key, item in value.items()}
    return value


class CheckpointResultRow(FlatArtifactModel):
    """Common checkpoint result contract for benchmark artifacts."""

    scenario_id: str
    checkpoint_id: str
    checkpoint_type: str
    success: bool
    passed: bool
    verdict: CheckpointVerdict
    score: float = Field(ge=0.0, le=1.0)
    review_required: bool
    failure_buckets: list[str] = Field(default_factory=list)
    warning_buckets: list[str] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any]


class CheckpointHorizonSection(BaseModel):
    """Typed checkpoint metadata flattened into checkpoint result artifacts."""

    family: str
    profile: str
    phase: str = "checkpoint"
    horizon_distance: int = Field(ge=0)
    horizon_distance_bucket: str
    interference_count: int = Field(ge=0)
    interference_count_bucket: str
    source_event_age_days: float = Field(ge=0.0)
    source_event_age_days_bucket: str
    required_retrieval_view: str
    expected_stage_path: list[str] = Field(default_factory=list)
    query_or_task: str

    model_config = ConfigDict(extra="forbid")

    def to_flat_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class CheckpointDecisionTraceSection(BaseModel):
    """Typed decision/runtime trace metadata flattened into checkpoint rows."""

    decision_mode: DecisionMode
    effective_decision_mode: DecisionMode
    llm_call_made: bool
    fallback_used: bool
    fallback_reason: str | None = None
    final_output_source: FinalOutputSource
    request_id: str

    model_config = ConfigDict(extra="forbid")

    def to_flat_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class CheckpointVerdictSection(BaseModel):
    """Typed verdict fields shared by simulator and runtime checkpoint rows."""

    success: bool
    passed: bool
    verdict: CheckpointVerdict
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    review_required: bool
    failure_buckets: list[str] = Field(default_factory=list)
    warning_buckets: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    def to_flat_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ChannelOverlapSection(BaseModel):
    """Role-channel overlap diagnostics for selected/support/rejected/context views."""

    critical: list[str] = Field(default_factory=list)
    warning: list[str] = Field(default_factory=list)
    critical_ids: dict[str, list[str]] = Field(default_factory=dict)
    warning_ids: dict[str, list[str]] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class SelectedClaimSupportClosureErrorSection(BaseModel):
    """Claim-local selected/supporting/citation closure diagnostics."""

    claim_id: str
    missing_supporting_claim: bool
    expected_event_ids: list[str] = Field(default_factory=list)
    present_event_ids: list[str] = Field(default_factory=list)
    missing_event_ids: list[str] = Field(default_factory=list)
    is_action_state: bool

    model_config = ConfigDict(extra="forbid")


class CheckpointDiagnosticsSection(BaseModel):
    """Typed diagnostics emitted by sim/runtime judge diagnostics."""

    missing_expected_ids: dict[str, list[str]] = Field(default_factory=dict)
    extra_selected_ids: dict[str, list[str]] = Field(default_factory=dict)
    allowed_definition_selected_ids: dict[str, list[str]] = Field(default_factory=dict)
    allowed_context_selected_ids: dict[str, list[str]] = Field(default_factory=dict)
    forbidden_selected_ids: dict[str, list[str]] = Field(default_factory=dict)
    answer_match_type: str
    failure_classification: list[str] = Field(default_factory=list)
    selected_excluded_ids: dict[str, list[str]] = Field(default_factory=dict)
    supporting_excluded_ids: dict[str, list[str]] = Field(default_factory=dict)
    rejected_expected_ids: dict[str, list[str]] = Field(default_factory=dict)
    missing_rejected_ids: dict[str, list[str]] = Field(default_factory=dict)
    missing_rejected_claim_subject_entity_ids: list[str] = Field(default_factory=list)
    supporting_wrong_entity_claim_ids: list[str] = Field(default_factory=list)
    supporting_wrong_subject_claim_ids: list[str] = Field(default_factory=list)
    supporting_wrong_subject_entity_ids: list[str] = Field(default_factory=list)
    supporting_disambiguation_claim_ids: list[str] = Field(default_factory=list)
    missing_wrong_entity_rejection_claim_ids: list[str] = Field(default_factory=list)
    missing_wrong_entity_rejection_subject_ids: list[str] = Field(default_factory=list)
    selected_noncurrent_claim_ids: list[str] = Field(default_factory=list)
    required_definition_claim_ids: list[str] = Field(default_factory=list)
    missing_definition_claim_ids: list[str] = Field(default_factory=list)
    missing_definition_support_claim_ids: list[str] = Field(default_factory=list)
    selected_entity_role_mismatches: list[str] = Field(default_factory=list)
    missing_selected_subject_entity_ids: list[str] = Field(default_factory=list)
    selected_object_entity_instead_of_subject_ids: list[str] = Field(default_factory=list)
    selected_graph_entity_overbreadth: list[str] = Field(default_factory=list)
    selected_nonrequired_graph_entity_ids: list[str] = Field(default_factory=list)
    selected_context_only_entity_ids: list[str] = Field(default_factory=list)
    selected_rejected_or_context_entity_ids: list[str] = Field(default_factory=list)
    supporting_noisy_citation_event_ids: list[str] = Field(default_factory=list)
    selected_claim_support_closure_errors: list[SelectedClaimSupportClosureErrorSection] = Field(default_factory=list)
    selected_claim_ids_missing_support: list[str] = Field(default_factory=list)
    selected_claim_evidence_event_ids_missing_support: list[str] = Field(default_factory=list)
    selected_action_state_event_ids_missing_support: list[str] = Field(default_factory=list)
    context_only_noise_event_ids: list[str] = Field(default_factory=list)
    supporting_role_violations: dict[str, list[str]] = Field(default_factory=dict)
    supporting_rejection_provenance_overlap: dict[str, list[str]] = Field(default_factory=dict)
    channel_overlap: ChannelOverlapSection = Field(default_factory=ChannelOverlapSection)
    role_misclassification: bool
    precision_failure_classification: list[str] = Field(default_factory=list)
    required_judge_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    def to_flat_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class NormalizationDiagnosticsSection(BaseModel):
    """Typed role-normalization diagnostics flattened into checkpoint rows."""

    auto_closed_selected_entity_ids: list[str] = Field(default_factory=list)
    auto_closed_rejected_entity_ids: list[str] = Field(default_factory=list)
    auto_closed_context_entity_ids: list[str] = Field(default_factory=list)
    auto_closed_context_relation_ids: list[str] = Field(default_factory=list)
    auto_promoted_selected_claim_ids: list[str] = Field(default_factory=list)
    auto_promoted_supporting_claim_ids: list[str] = Field(default_factory=list)
    auto_promoted_supporting_citation_event_ids: list[str] = Field(default_factory=list)
    auto_rejected_claim_ids: list[str] = Field(default_factory=list)
    normalization_reason_codes: list[str] = Field(default_factory=list)
    normalization_applied: bool

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def from_normalization(cls, normalization: Any) -> NormalizationDiagnosticsSection:
        return cls(
            auto_closed_selected_entity_ids=list(normalization.auto_closed_selected_entity_ids),
            auto_closed_rejected_entity_ids=list(normalization.auto_closed_rejected_entity_ids),
            auto_closed_context_entity_ids=list(normalization.auto_closed_context_entity_ids),
            auto_closed_context_relation_ids=list(normalization.auto_closed_context_relation_ids),
            auto_promoted_selected_claim_ids=list(normalization.auto_promoted_selected_claim_ids),
            auto_promoted_supporting_claim_ids=list(normalization.auto_promoted_supporting_claim_ids),
            auto_promoted_supporting_citation_event_ids=list(normalization.auto_promoted_supporting_citation_event_ids),
            auto_rejected_claim_ids=list(normalization.auto_rejected_claim_ids),
            normalization_reason_codes=list(normalization.normalization_reason_codes),
            normalization_applied=bool(normalization.normalization_applied),
        )

    def to_flat_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class RuntimeDiagnosticsSection(BaseModel):
    """Typed runtime-only diagnostics flattened into runtime checkpoint rows."""

    runtime_graph_validation_errors: list[str] = Field(default_factory=list)
    runtime_relation_support: list[dict[str, Any]] = Field(default_factory=list)
    runtime_action_support: list[dict[str, Any]] = Field(default_factory=list)
    runtime_action_alignments: list[dict[str, Any]] = Field(default_factory=list)
    runtime_execution_state: dict[str, Any] = Field(default_factory=dict)
    active_continuation_branch: Any = None
    suppressed_branch_ids: list[str] = Field(default_factory=list)
    action_alignment_failure_reason: str = ""

    model_config = ConfigDict(extra="forbid")

    def to_flat_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class SimCheckpointResultRow(CheckpointResultRow):
    """Checkpoint row emitted by ``memory_evolution_sim_v1``."""

    profile: str
    family: str
    decision_mode: DecisionMode
    effective_decision_mode: DecisionMode
    final_output_source: FinalOutputSource


class RuntimeCheckpointResultRow(SimCheckpointResultRow):
    """Checkpoint row emitted by ``memory_evolution_runtime_v1``."""

    runtime_failure_buckets: list[str] = Field(default_factory=list)
    runtime_failure_classification: list[str] = Field(default_factory=list)
    scenario_provider_successes: int = Field(default=0, ge=0)
    scenario_provider_failures: int = Field(default=0, ge=0)
    scenario_fallbacks: int = Field(default=0, ge=0)
    provider_count_scope: ProviderCountScope = "scenario_extractor_calls"


class JudgeVoteRow(FlatArtifactModel):
    """Stable row contract for flattened judge votes."""

    judge_id: str
    checkpoint_id: str
    verdict: CheckpointVerdict
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    covered_ids: list[str] = Field(default_factory=list)
    failed_ids: list[str] = Field(default_factory=list)
    abstained_ids: list[str] = Field(default_factory=list)
    failure_buckets: list[str] = Field(default_factory=list)
    rationale: str


class RuntimeGraphAlignmentRow(FlatArtifactModel):
    """Stable alignment row contract for runtime graph-to-oracle artifacts."""

    scenario_id: str
    checkpoint_id: str
    oracle_id: str
    runtime_id: str
    item_type: AlignmentItemType
    verdict: AlignmentVerdict
    score: float = Field(ge=0.0, le=1.0)
    matched_on: list[str] = Field(default_factory=list)
    failure_reason: str

    @classmethod
    def from_runtime_alignment(cls, row: dict[str, object]) -> RuntimeGraphAlignmentRow:
        enriched = {
            **row,
            "oracle_id": str(row.get("oracle_id") or row.get("oracle_item_id") or ""),
            "runtime_id": str(row.get("runtime_id") or row.get("runtime_item_id") or ""),
            "failure_reason": str(row.get("failure_reason") or row.get("rationale") or ""),
        }
        return cls.from_flat_row(enriched)

    @model_validator(mode="after")
    def validate_identity_by_verdict(self) -> RuntimeGraphAlignmentRow:
        verdict = self.verdict
        has_oracle = bool(self.oracle_id)
        has_runtime = bool(self.runtime_id)
        if verdict in {"aligned", "partial"} and not (has_oracle and has_runtime):
            raise ValueError(f"{verdict} graph alignment rows require oracle_id and runtime_id")
        if verdict == "missing_expected" and not has_oracle:
            raise ValueError("missing_expected graph alignment rows require oracle_id")
        if verdict == "unmatched_runtime" and not has_runtime:
            raise ValueError("unmatched_runtime graph alignment rows require runtime_id")
        if verdict == "ambiguous_alignment" and not (has_oracle or has_runtime):
            raise ValueError("ambiguous graph alignment rows require oracle_id or runtime_id")
        if verdict != "aligned" and not self.failure_reason:
            raise ValueError(f"{verdict} graph alignment rows require failure_reason")
        return self


class RuntimeActionAlignmentRow(FlatArtifactModel):
    """Stable row contract for runtime action-to-oracle alignment diagnostics."""

    expected_action_id: str
    runtime_action_id: str
    runtime_item_id: str
    verdict: AlignmentVerdict
    support_mode: ActionSupportMode
    matched_on: list[str] = Field(default_factory=list)
    failed_on: list[str] = Field(default_factory=list)
    failure_reason: str
    evidence_event_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_identity_by_verdict(self) -> RuntimeActionAlignmentRow:
        has_runtime = bool(self.runtime_action_id or self.runtime_item_id)
        if self.verdict == "aligned" and not has_runtime:
            raise ValueError("aligned action rows require runtime_action_id or runtime_item_id")
        if self.verdict == "partial" and not has_runtime:
            raise ValueError("partial action rows require runtime_action_id or runtime_item_id")
        if self.verdict == "missing_expected" and not self.failure_reason:
            raise ValueError("missing_expected action rows require failure_reason")
        if self.verdict == "ambiguous_alignment" and not has_runtime:
            raise ValueError("ambiguous action rows require runtime_action_id or runtime_item_id")
        if self.verdict != "aligned" and not self.failure_reason:
            raise ValueError(f"{self.verdict} action rows require failure_reason")
        return self


class RuntimeGraphSummary(FlatArtifactModel):
    """Stable summary contract for runtime graph completeness metrics."""

    source_observation_count: int = Field(ge=0)
    entity_count: int = Field(ge=0)
    claim_count: int = Field(ge=0)
    action_count: int = Field(ge=0)
    relation_item_count: int = Field(ge=0)
    action_item_count: int = Field(ge=0)
    graph_edge_count: int = Field(ge=0)
    graph_edge_counts_by_type: dict[str, int] = Field(default_factory=dict)
    runtime_graph_node_counts_by_type: dict[str, int] = Field(default_factory=dict)
    runtime_graph_item_counts_by_type: dict[str, int] = Field(default_factory=dict)
    runtime_relation_support_modes: dict[str, int] = Field(default_factory=dict)
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


class AlignmentSummary(FlatArtifactModel):
    """Stable summary contract for runtime graph alignment artifacts."""

    alignment_summary_policy: dict[str, str]
    checkpoint_expected_alignment_audit_count: int = Field(ge=0)
    checkpoint_expected_alignment_audit_counts: dict[str, int] = Field(default_factory=dict)
    checkpoint_expected_alignment_audit_counts_by_item_type: dict[str, int] = Field(default_factory=dict)
    checkpoint_scored_verdict_counts: dict[str, int] = Field(default_factory=dict)
    checkpoint_scored_review_required_count: int = Field(ge=0)
    checkpoint_scored_failure_bucket_counts: dict[str, int] = Field(default_factory=dict)
    full_graph_audit_alignment_count: int = Field(ge=0)
    full_graph_audit_alignment_counts: dict[str, int] = Field(default_factory=dict)
    full_graph_audit_alignment_counts_by_item_type: dict[str, int] = Field(default_factory=dict)


class WarningExampleRow(FlatArtifactModel):
    """Stable row contract for warning-only examples."""

    scenario_id: str
    checkpoint_id: str
    checkpoint_type: str
    warning_bucket: str
    warning_buckets: list[str]
    reason: str


class BenchmarkReportSummary(FlatArtifactModel):
    """Minimum stable report contract shared by benchmark report.json files."""

    suite: BenchmarkSuiteName
    mode: DecisionMode
    profile: str
    seed: int
    benchmark_key: str = ""
    run_id: str = ""
    generated_at: str = ""
    fixture_source: str = ""
    fixture_hashes: dict[str, str] = Field(default_factory=dict)
    scenario_count: int = Field(ge=0)
    validation_scenario_catalog: list[dict[str, Any]] = Field(default_factory=list)
    event_count: int = Field(ge=0)
    checkpoint_count: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    llm_calls: int = Field(ge=0)
    provider_successes: int = Field(ge=0)
    provider_failures: int = Field(ge=0)
    fallbacks: int = Field(ge=0)
    final_output_source_counts: dict[str, int] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    long_horizon_slice_counts: dict[str, Any] = Field(default_factory=dict)
    calibration: CalibrationReport | dict[str, Any] = Field(default_factory=dict)
    decision_quality: DecisionCostReport | dict[str, Any] = Field(default_factory=dict)
    failure_bucket_counts: dict[str, int] = Field(default_factory=dict)
    critical_failure_bucket_counts: dict[str, int] = Field(default_factory=dict)
    warning_bucket_counts: dict[str, int] = Field(default_factory=dict)
    review_bucket_counts: dict[str, int] = Field(default_factory=dict)
    judge_metrics: dict[str, Any] = Field(default_factory=dict)
    baseline_scores: dict[str, Any] = Field(default_factory=dict)
    artifact_version: int = Field(default=1, ge=1)
    scenario_results: list[dict[str, Any]] = Field(default_factory=list)
    checkpoint_results: list[dict[str, Any]] = Field(default_factory=list)
    runtime: dict[str, Any] = Field(default_factory=dict)
    runtime_graph_summary: RuntimeGraphSummary | dict[str, Any] = Field(default_factory=dict)
    runtime_graph_alignments_summary: AlignmentSummary | dict[str, Any] = Field(default_factory=dict)
    runtime_failure_bucket_counts: dict[str, int] = Field(default_factory=dict)
    warning_policy: dict[str, Any] = Field(default_factory=dict)
    hidden_item_count: float | int | None = None
    hidden_hallucination_rate: float | int | None = None
    hidden_answer_leak_rate: float | int | None = None

    @model_validator(mode="after")
    def validate_nested_report_sections(self) -> BenchmarkReportSummary:
        calibration_required = self.suite in _CALIBRATION_REQUIRED_SUITES
        if isinstance(self.runtime_graph_summary, dict) and self.runtime_graph_summary:
            self.runtime_graph_summary = RuntimeGraphSummary.from_flat_row(self.runtime_graph_summary)
        if isinstance(self.runtime_graph_alignments_summary, dict) and self.runtime_graph_alignments_summary:
            self.runtime_graph_alignments_summary = AlignmentSummary.from_flat_row(self.runtime_graph_alignments_summary)
        if isinstance(self.calibration, dict) and self.calibration:
            self.calibration = CalibrationReport.model_validate(self.calibration)
        elif calibration_required and isinstance(self.calibration, dict):
            raise ValueError(f"{self.suite} report requires calibration")
        if isinstance(self.decision_quality, dict) and self.decision_quality:
            self.decision_quality = DecisionCostReport.model_validate(self.decision_quality)
        elif calibration_required and isinstance(self.decision_quality, dict):
            raise ValueError(f"{self.suite} report requires decision_quality")
        return self


def checkpoint_warning_buckets(
    *,
    answer_match_type: object,
    output: dict[str, object],
) -> list[str]:
    """Return warning-only artifact buckets shared by sim/runtime rows."""

    buckets: list[str] = []
    if answer_match_type == "optional_missing":
        buckets.append("graph_answer_optional_missing")
    if (
        output.get("context_claim_ids")
        or output.get("context_entity_ids")
        or output.get("context_relation_ids")
        or output.get("context_citation_event_ids")
    ):
        buckets.append("extra_context_provenance")
    return buckets
