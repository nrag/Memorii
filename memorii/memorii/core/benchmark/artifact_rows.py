"""Typed benchmark artifact contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from enum import Enum
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator, model_validator

from memorii.core.benchmark.memory_evolution_sim.schemas import (
    JudgeAggregate,
    MemoryEvolutionSimReconstructionContext,
    OracleCheckpoint,
    SimSystemOutput,
)
from memorii.core.calibration.models import CalibrationReport, DecisionCostReport
from memorii.core.memory_evolution.execution import ContinuationDecision, WorkState, WorkStateSnapshot
from memorii.core.memory_evolution.retrieval import ProductionRetrievalDecision

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
FinalOutputSource: TypeAlias = Literal["rule", "fake_oracle", "live_llm", "llm", "mixed", "reused_runtime_state"]
ProviderCountScope: TypeAlias = Literal["scenario_extractor_calls"]
ProviderHealthStatus: TypeAlias = Literal["pass", "fail", "not_applicable"]
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
JsonScalar: TypeAlias = str | int | float | bool | None


def _validate_json_value(value: object, *, path: str = "value") -> None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} contains a non-string JSON object key")
            _validate_json_value(item, path=f"{path}.{key}")
        return
    raise ValueError(f"{path} contains a non-JSON value of type {type(value).__name__}")


class ArtifactJsonObject(RootModel[dict[str, object]], Mapping[str, object]):
    """Explicitly open JSON object for intentionally dynamic report payloads.

    Benchmark metric namespaces evolve independently of the stable report
    envelope. Keeping this boundary recursive and JSON-only prevents arbitrary
    Python objects from entering artifacts while avoiding a false schema for
    every suite-specific metric.
    """

    def __getitem__(self, key: str) -> object:
        return self.root[key]

    def __iter__(self):
        return iter(self.root)

    def __len__(self) -> int:
        return len(self.root)

    @field_validator("root")
    @classmethod
    def _json_only(cls, value: dict[str, object]) -> dict[str, object]:
        _validate_json_value(value)
        return value

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ArtifactJsonObject):
            return self.root == other.root
        if isinstance(other, dict):
            return self.root == other
        return NotImplemented

    def to_json_object(self) -> dict[str, object]:
        return self.root


def _empty_json_object() -> ArtifactJsonObject:
    return ArtifactJsonObject(root={})


class FlatArtifactModel(BaseModel, Mapping[str, object]):
    """Strict artifact model with an explicit JSON serialization boundary."""

    model_config = ConfigDict(extra="forbid")

    def __getitem__(self, key: str) -> object:
        values = self.model_dump(mode="python")
        return _artifact_value_to_json(values[key])

    def __len__(self) -> int:
        return len(self.model_fields)

    def __iter__(self):
        return iter(self.model_dump(mode="python"))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Mapping):
            return self.to_json_row() == dict(other)
        return super().__eq__(other)

    @classmethod
    def from_flat_row(cls, row: dict[str, object]) -> FlatArtifactModel:
        return cls.model_validate(row)

    def to_json_row(self) -> dict[str, object]:
        return _artifact_value_to_json(self.model_dump(mode="python"))


def artifact_row_to_json(row: FlatArtifactModel) -> dict[str, object]:
    """Serialize a validated artifact row at an explicit JSON boundary."""

    return row.to_json_row()


def artifact_rows_to_json(rows: Sequence[FlatArtifactModel]) -> list[dict[str, object]]:
    """Serialize artifact rows at explicit JSON/report boundaries."""

    return [artifact_row_to_json(row) for row in rows]


def _artifact_value_to_json(value: object) -> object:
    if isinstance(value, FlatArtifactModel):
        return value.to_json_row()
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_artifact_value_to_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _artifact_value_to_json(item) for key, item in value.items()}
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


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


class CheckpointResultRow(FlatArtifactModel):
    """Common checkpoint result contract for benchmark artifacts."""

    scenario_id: str
    checkpoint_id: str
    checkpoint_type: str
    success: bool
    passed: bool
    verdict: CheckpointVerdict
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    review_required: bool
    failure_buckets: list[str] = Field(default_factory=list)
    warning_buckets: list[str] = Field(default_factory=list)
    diagnostics: CheckpointDiagnosticsPayload = Field(default_factory=lambda: CheckpointDiagnosticsPayload())
    output: SimSystemOutput
    phase: str = "checkpoint"
    horizon_distance: int = Field(default=0, ge=0)
    horizon_distance_bucket: str = "short"
    interference_count: int = Field(default=0, ge=0)
    interference_count_bucket: str = "none"
    source_event_age_days: float = Field(default=0.0, ge=0.0)
    source_event_age_days_bucket: str = "fresh"
    required_retrieval_view: str = "current"
    expected_stage_path: list[str] = Field(default_factory=list)
    query_or_task: str = ""
    llm_call_made: bool = False
    fallback_used: bool = False
    fallback_reason: str | None = None
    request_id: str = ""
    expected: OracleCheckpoint
    candidate_cards: MemoryEvolutionSimReconstructionContext
    raw_output: SimSystemOutput
    normalized_output: SimSystemOutput
    judge_aggregate: JudgeAggregate
    # These high-value judge diagnostics remain top-level because artifact
    # consumers use them for filtering without joining or unpacking payloads.
    # The complete typed diagnostic section is also retained under diagnostics.
    selected_excluded_ids: dict[str, list[str]] = Field(default_factory=dict)
    supporting_excluded_ids: dict[str, list[str]] = Field(default_factory=dict)
    missing_expected_ids: dict[str, list[str]] = Field(default_factory=dict)
    extra_selected_ids: dict[str, list[str]] = Field(default_factory=dict)
    allowed_definition_selected_ids: dict[str, list[str]] = Field(default_factory=dict)
    allowed_context_selected_ids: dict[str, list[str]] = Field(default_factory=dict)
    forbidden_selected_ids: dict[str, list[str]] = Field(default_factory=dict)
    answer_match_type: str = "unknown"
    failure_classification: list[str] = Field(default_factory=list)
    rejected_expected_ids: dict[str, list[str]] = Field(default_factory=dict)
    missing_rejected_ids: dict[str, list[str]] = Field(default_factory=dict)
    missing_rejected_claim_subject_entity_ids: list[str] = Field(default_factory=list)
    supporting_wrong_entity_claim_ids: list[str] = Field(default_factory=list)
    selected_noncurrent_claim_ids: list[str] = Field(default_factory=list)
    supporting_noisy_citation_event_ids: list[str] = Field(default_factory=list)
    supporting_wrong_subject_claim_ids: list[str] = Field(default_factory=list)
    supporting_wrong_subject_entity_ids: list[str] = Field(default_factory=list)
    supporting_disambiguation_claim_ids: list[str] = Field(default_factory=list)
    missing_wrong_entity_rejection_claim_ids: list[str] = Field(default_factory=list)
    missing_wrong_entity_rejection_subject_ids: list[str] = Field(default_factory=list)
    context_only_noise_event_ids: list[str] = Field(default_factory=list)
    required_definition_claim_ids: list[str] = Field(default_factory=list)
    missing_definition_claim_ids: list[str] = Field(default_factory=list)
    missing_definition_support_claim_ids: list[str] = Field(default_factory=list)
    rejected_required_definition_claim_ids: list[str] = Field(default_factory=list)
    selected_entity_role_mismatches: list[str] = Field(default_factory=list)
    missing_selected_subject_entity_ids: list[str] = Field(default_factory=list)
    selected_object_entity_instead_of_subject_ids: list[str] = Field(default_factory=list)
    selected_graph_entity_overbreadth: list[str] = Field(default_factory=list)
    selected_nonrequired_graph_entity_ids: list[str] = Field(default_factory=list)
    selected_context_only_entity_ids: list[str] = Field(default_factory=list)
    selected_rejected_or_context_entity_ids: list[str] = Field(default_factory=list)
    selected_claim_support_closure_errors: list[SelectedClaimSupportClosureErrorSection] = Field(default_factory=list)
    selected_claim_ids_missing_support: list[str] = Field(default_factory=list)
    selected_claim_evidence_event_ids_missing_support: list[str] = Field(default_factory=list)
    selected_action_state_event_ids_missing_support: list[str] = Field(default_factory=list)
    supporting_role_violations: dict[str, list[str]] = Field(default_factory=dict)
    supporting_rejection_provenance_overlap: dict[str, list[str]] = Field(default_factory=dict)
    channel_overlap: ChannelOverlapSection = Field(default_factory=ChannelOverlapSection)
    required_judge_ids: list[str] = Field(default_factory=list)
    role_misclassification: bool = False
    precision_failure_classification: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_verdict_projection(self) -> CheckpointResultRow:
        expected_passed = self.verdict == "pass"
        if self.passed != expected_passed:
            raise ValueError("checkpoint passed must be true exactly when verdict is pass")
        return self


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

    def to_flat_fields(self) -> dict[str, object]:
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

    def to_flat_fields(self) -> dict[str, object]:
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

    def to_flat_fields(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class CheckpointDiagnosticsSection(BaseModel):
    """Typed diagnostics emitted by sim/runtime judge diagnostics."""

    missing_expected_ids: dict[str, list[str]] = Field(default_factory=dict)
    extra_selected_ids: dict[str, list[str]] = Field(default_factory=dict)
    allowed_definition_selected_ids: dict[str, list[str]] = Field(default_factory=dict)
    allowed_context_selected_ids: dict[str, list[str]] = Field(default_factory=dict)
    forbidden_selected_ids: dict[str, list[str]] = Field(default_factory=dict)
    answer_match_type: str = "unknown"
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
    rejected_required_definition_claim_ids: list[str] = Field(default_factory=list)
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
    role_misclassification: bool = False
    precision_failure_classification: list[str] = Field(default_factory=list)
    required_judge_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    def to_flat_fields(self) -> dict[str, object]:
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
    auto_demoted_execution_context_claim_ids: list[str] = Field(default_factory=list)
    repaired_definition_claim_conflict_ids: list[str] = Field(default_factory=list)
    auto_rejected_claim_ids: list[str] = Field(default_factory=list)
    normalization_reason_codes: list[str] = Field(default_factory=list)
    normalization_applied: bool

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def from_normalization(cls, normalization: object) -> NormalizationDiagnosticsSection:
        return cls(
            auto_closed_selected_entity_ids=list(normalization.auto_closed_selected_entity_ids),
            auto_closed_rejected_entity_ids=list(normalization.auto_closed_rejected_entity_ids),
            auto_closed_context_entity_ids=list(normalization.auto_closed_context_entity_ids),
            auto_closed_context_relation_ids=list(normalization.auto_closed_context_relation_ids),
            auto_promoted_selected_claim_ids=list(normalization.auto_promoted_selected_claim_ids),
            auto_promoted_supporting_claim_ids=list(normalization.auto_promoted_supporting_claim_ids),
            auto_promoted_supporting_citation_event_ids=list(normalization.auto_promoted_supporting_citation_event_ids),
            auto_demoted_execution_context_claim_ids=list(normalization.auto_demoted_execution_context_claim_ids),
            repaired_definition_claim_conflict_ids=list(normalization.repaired_definition_claim_conflict_ids),
            auto_rejected_claim_ids=list(normalization.auto_rejected_claim_ids),
            normalization_reason_codes=list(normalization.normalization_reason_codes),
            normalization_applied=bool(normalization.normalization_applied),
        )

    def to_flat_fields(self) -> dict[str, object]:
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
    provider_successes: int = Field(default=0, ge=0)
    provider_failures: int = Field(default=0, ge=0)
    fallbacks: int = Field(default=0, ge=0)
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
    def from_runtime_alignment(cls, row: Mapping[str, object]) -> RuntimeGraphAlignmentRow:
        return cls(
            scenario_id=str(row.get("scenario_id", "")),
            checkpoint_id=str(row.get("checkpoint_id", "")),
            oracle_id=str(row.get("oracle_id") or row.get("oracle_item_id") or ""),
            runtime_id=str(row.get("runtime_id") or row.get("runtime_item_id") or ""),
            item_type=str(row.get("item_type", "claim")),
            verdict=str(row.get("verdict", "missing_expected")),
            score=float(row.get("score", 0.0)),
            matched_on=[str(item) for item in row.get("matched_on", []) or []],
            failure_reason=str(row.get("failure_reason") or row.get("rationale") or ""),
        )

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
    status: str = ""
    target_entity_ids: list[str] = Field(default_factory=list)
    continuation_rank: int = 0
    model_status_raw: str = ""
    action_type_raw: str = ""
    status_derived_from: str = ""
    bridged_target_entity_id: str | None = None

    @classmethod
    def from_runtime_alignment(cls, row: Mapping[str, object]) -> RuntimeActionAlignmentRow:
        return cls(
            expected_action_id=str(row.get("expected_action_id", "")),
            runtime_action_id=str(row.get("runtime_action_id", "")),
            runtime_item_id=str(row.get("runtime_item_id", "")),
            verdict=str(row.get("verdict", "missing_expected")),
            support_mode=str(row.get("support_mode", "missing_action")),
            matched_on=[str(item) for item in row.get("matched_on", []) or []],
            failed_on=[str(item) for item in row.get("failed_on", []) or []],
            failure_reason=str(row.get("failure_reason", "")),
            evidence_event_ids=[str(item) for item in row.get("evidence_event_ids", []) or []],
            status=str(row.get("status", "")),
            target_entity_ids=[str(item) for item in row.get("target_entity_ids", []) or []],
            continuation_rank=int(row.get("continuation_rank", 0) or 0),
            model_status_raw=str(row.get("model_status_raw", "")),
            action_type_raw=str(row.get("action_type_raw", "")),
            status_derived_from=str(row.get("status_derived_from", "")),
            bridged_target_entity_id=(
                str(row["bridged_target_entity_id"])
                if row.get("bridged_target_entity_id")
                else None
            ),
        )

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


class RuntimeRelationSupportRow(BaseModel):
    """Typed relation-support diagnostics for runtime checkpoint artifacts."""

    relation_id: str
    support_mode: str

    model_config = ConfigDict(extra="forbid")


class RuntimeActionSupportRow(BaseModel):
    """Typed action-support diagnostics for runtime checkpoint artifacts."""

    action_id: str
    support_mode: str

    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionStateSection(FlatArtifactModel):
    """Typed production execution projection retained for auditability."""

    status: str | None = None
    reason: str | None = None
    active_continuation_branch: str | None = None
    active_runtime_continuation_branch: str | None = None
    active_evidence_event_ids: list[str] = Field(default_factory=list)
    suppressed_branch_ids: list[str] = Field(default_factory=list)
    ambiguous_action_count: int = Field(default=0, ge=0)
    aligned_action_count: int = Field(default=0, ge=0)
    decision_status: str | None = None
    decision_abstained: bool | None = None
    active_branch_ids: list[str] = Field(default_factory=list)
    states: list[WorkState] = Field(default_factory=list)
    ambiguous_branch_ids: list[str] = Field(default_factory=list)
    continuation_decision: ContinuationDecision | None = None
    production_work_state: WorkStateSnapshot | None = None

    model_config = ConfigDict(extra="forbid")


class RuntimeDiagnosticsSection(BaseModel):
    """Typed runtime diagnostics flattened into checkpoint rows."""

    runtime_graph_validation_errors: list[str] = Field(default_factory=list)
    runtime_relation_support: list[RuntimeRelationSupportRow] = Field(default_factory=list)
    runtime_action_support: list[RuntimeActionSupportRow] = Field(default_factory=list)
    runtime_action_alignments: list[RuntimeActionAlignmentRow] = Field(default_factory=list)
    runtime_execution_state: RuntimeExecutionStateSection
    runtime_retrieval_decision: ProductionRetrievalDecision | None = None
    active_continuation_branch: str | None = None
    suppressed_branch_ids: list[str] = Field(default_factory=list)
    action_alignment_failure_reason: str

    model_config = ConfigDict(extra="forbid")

    def to_flat_fields(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class CheckpointDiagnosticsPayload(CheckpointDiagnosticsSection):
    """Complete typed payload persisted under a checkpoint's diagnostics key."""

    auto_closed_selected_entity_ids: list[str] = Field(default_factory=list)
    auto_closed_rejected_entity_ids: list[str] = Field(default_factory=list)
    auto_closed_context_entity_ids: list[str] = Field(default_factory=list)
    auto_closed_context_relation_ids: list[str] = Field(default_factory=list)
    auto_promoted_selected_claim_ids: list[str] = Field(default_factory=list)
    auto_promoted_supporting_claim_ids: list[str] = Field(default_factory=list)
    auto_promoted_supporting_citation_event_ids: list[str] = Field(default_factory=list)
    auto_demoted_execution_context_claim_ids: list[str] = Field(default_factory=list)
    repaired_definition_claim_conflict_ids: list[str] = Field(default_factory=list)
    auto_rejected_claim_ids: list[str] = Field(default_factory=list)
    normalization_reason_codes: list[str] = Field(default_factory=list)
    normalization_applied: bool = False
    runtime_graph_validation_errors: list[str] = Field(default_factory=list)
    runtime_relation_support: list[RuntimeRelationSupportRow] = Field(default_factory=list)
    runtime_action_support: list[RuntimeActionSupportRow] = Field(default_factory=list)
    runtime_action_alignments: list[RuntimeActionAlignmentRow] = Field(default_factory=list)
    runtime_execution_state: RuntimeExecutionStateSection | None = None
    runtime_retrieval_decision: ProductionRetrievalDecision | None = None
    active_continuation_branch: str | None = None
    suppressed_branch_ids: list[str] = Field(default_factory=list)
    action_alignment_failure_reason: str = ""


RuntimeDiagnosticsSection.model_rebuild()
CheckpointDiagnosticsSection.model_rebuild()
CheckpointDiagnosticsPayload.model_rebuild()
CheckpointResultRow.model_rebuild()
SimCheckpointResultRow.model_rebuild()
RuntimeCheckpointResultRow.model_rebuild()


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
    snapshot_count: int = Field(default=0, ge=0)
    aggregation_scope: Literal["final_snapshot_per_scenario"] = "final_snapshot_per_scenario"
    cumulative_graph_edge_count: int = Field(default=0, ge=0)
    cumulative_validation_error_count: int = Field(default=0, ge=0)
    terminal_snapshot_count: int = Field(default=0, ge=0)
    terminal_snapshot_anomaly_count: int = Field(default=0, ge=0)


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
    failure_classification_counts: dict[str, int] = Field(default_factory=dict)
    execution_source: FinalOutputSource
    dry_run: bool
    fake_extractor_calls: int = Field(default=0, ge=0)
    provider_metadata: dict[str, str] = Field(default_factory=dict)
    policy: dict[str, str]


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

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Mapping):
            expected = dict(other)
            actual = {key: value for key, value in self.to_json_row().items() if value not in (None, "")}
            return actual == expected
        return super().__eq__(other)


class ValidationScenarioCatalogRow(FlatArtifactModel):
    scenario_id: str
    family: str
    profile: str
    observation_count: int = Field(ge=0)
    checkpoint_count: int = Field(ge=0)
    checkpoint_types: list[str] = Field(default_factory=list)
    difficulty_tags: list[str] = Field(default_factory=list)
    phase_counts: dict[str, int] = Field(default_factory=dict)
    max_horizon_distance: int = Field(ge=0)
    max_interference_count: int = Field(ge=0)
    hidden_item_count: int = Field(ge=0)
    observed_claim_count: int = Field(ge=0)
    inferable_claim_count: int = Field(ge=0)


class SimScenarioResultRow(FlatArtifactModel):
    scenario_id: str
    family: str
    profile: str
    decision_mode: DecisionMode
    effective_decision_mode: DecisionMode
    checkpoint_count: int = Field(ge=0)
    success: bool
    failure_mode: str | None = None
    checkpoints_passed: int = Field(ge=0)
    checkpoints_failed: int = Field(ge=0)


class BenchmarkReportSummary(FlatArtifactModel):
    """Minimum stable report contract shared by benchmark report.json files."""

    suite: BenchmarkSuiteName
    mode: DecisionMode
    profile: str
    seed: int
    benchmark_key: str = ""
    run_config_fingerprint: str = ""
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
    final_output_source_counts: dict[str, int] = Field(default_factory=dict)
    metrics: ArtifactJsonObject = Field(default_factory=_empty_json_object)
    long_horizon_slice_counts: ArtifactJsonObject = Field(default_factory=_empty_json_object)
    calibration: CalibrationReport | ArtifactJsonObject = Field(default_factory=_empty_json_object)
    decision_quality: DecisionCostReport | ArtifactJsonObject = Field(default_factory=_empty_json_object)
    failure_bucket_counts: dict[str, int] = Field(default_factory=dict)
    critical_failure_bucket_counts: dict[str, int] = Field(default_factory=dict)
    warning_bucket_counts: dict[str, int] = Field(default_factory=dict)
    review_bucket_counts: dict[str, int] = Field(default_factory=dict)
    judge_metrics: ArtifactJsonObject = Field(default_factory=_empty_json_object)
    baseline_scores: ArtifactJsonObject = Field(default_factory=_empty_json_object)
    artifact_version: int = Field(default=1, ge=1)
    scenario_results: list[SimScenarioResultRow] = Field(default_factory=list)
    # The simulator row is the strict base shape; runtime-only fields are
    # required for runtime rows and therefore make the second union branch
    # win only when those fields are present.
    checkpoint_results: list[SimCheckpointResultRow | RuntimeCheckpointResultRow] = Field(default_factory=list)
    runtime: ArtifactJsonObject = Field(default_factory=_empty_json_object)
    runtime_graph_summary: RuntimeGraphSummary | ArtifactJsonObject = Field(default_factory=_empty_json_object)
    runtime_graph_alignments_summary: AlignmentSummary | ArtifactJsonObject = Field(default_factory=_empty_json_object)
    runtime_failure_bucket_counts: dict[str, int] = Field(default_factory=dict)
    runtime_provider_health: RuntimeProviderHealth | ArtifactJsonObject = Field(default_factory=_empty_json_object)
    warning_policy: dict[str, WarningPolicyEntry] = Field(default_factory=dict)
    hidden_item_count: int | None = Field(default=None, ge=0)
    hidden_hallucination_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    hidden_answer_leak_rate: float | None = Field(default=None, ge=0.0, le=1.0)

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
        if self.dry_run and any((self.provider_successes, self.provider_failures, self.fallbacks)):
            raise ValueError("dry-run reports cannot contain provider successes, failures, or fallbacks")
        if self.execution_source == "fake_oracle" and not self.dry_run:
            raise ValueError("fake_oracle is only valid for dry-run reports")
        calibration_required = self.suite in _CALIBRATION_REQUIRED_SUITES
        if isinstance(self.runtime_graph_summary, ArtifactJsonObject) and self.runtime_graph_summary.root:
            self.runtime_graph_summary = RuntimeGraphSummary.from_flat_row(self.runtime_graph_summary.root)
        if isinstance(self.runtime_graph_alignments_summary, ArtifactJsonObject) and self.runtime_graph_alignments_summary.root:
            self.runtime_graph_alignments_summary = AlignmentSummary.from_flat_row(self.runtime_graph_alignments_summary.root)
        if isinstance(self.runtime_provider_health, ArtifactJsonObject) and self.runtime_provider_health.root:
            self.runtime_provider_health = RuntimeProviderHealth.from_flat_row(self.runtime_provider_health.root)
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
        if isinstance(self.runtime_provider_health, RuntimeProviderHealth):
            health = self.runtime_provider_health
            if health.provider_successes != self.provider_successes:
                raise ValueError("top-level and runtime provider success counts disagree")
            if health.provider_failures != self.provider_failures:
                raise ValueError("top-level and runtime provider failure counts disagree")
            if health.fallbacks != self.fallbacks:
                raise ValueError("top-level and runtime fallback counts disagree")
        if isinstance(self.runtime_graph_alignments_summary, AlignmentSummary):
            scored = self.runtime_graph_alignments_summary.checkpoint_scored_verdict_counts
            if scored and sum(scored.values()) != self.checkpoint_count:
                raise ValueError("scored checkpoint verdict counts must sum to checkpoint_count")
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
