"""Runtime benchmark row and projection models."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Literal, TypeAlias, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter, model_validator

from memorii.core.benchmark.artifact_rows import (
    FlatArtifactModel,
    RuntimeActionAlignmentRow,
    RuntimeChannelAlignmentRow,
    RuntimeCheckpointResultRow,
    RuntimeExecutionStateSection,
    RuntimeExtractorTraceRow,
    RuntimeGraphAlignmentRow,
    SimScenarioResultRow,
)
from memorii.core.benchmark.calibration.alignment import RuntimeGraphAlignment
from memorii.core.benchmark.memory_evolution_sim import JudgeAggregate, SimSystemOutput
from memorii.core.memory_evolution import (
    ClaimLifecycleTransition,
    EntityIdentityDecision,
    EntityMention,
    ExtractedAction,
    ExtractedClaim,
    ExtractedIdentityRelation,
    ExtractionFailureCode,
    ExtractionRunStatus,
    FallbackOutcome,
    FinalExtractionSource,
    MemoryGraphEdge,
    MemoryGraphNode,
    MemoryGraphSnapshot,
    ProductionRetrievalDecision,
    ProviderAttemptStatus,
    RecordLifecycleState,
    ValidationResult,
    WorkStateSnapshot,
    WorkStateStatus,
)
from memorii.core.memory_evolution.extraction_contracts import MemoryExtractionOutput
from memorii.core.memory_evolution.operation_models import (
    EvolutionFailureCategory,
    EvolutionOperationStatus,
)

if TYPE_CHECKING:
    from memorii.core.benchmark.memory_evolution_runtime.ingestion_oracle import (
        IngestionPrefixAuditRow,
    )
    from memorii.core.benchmark.memory_evolution_runtime.semantic_comparison import (
        SemanticComparisonResult,
    )

T = TypeVar("T")
NonEmptyString: TypeAlias = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class RuntimeGraphSnapshotRow(BaseModel):
    """Typed graph snapshot persisted by the runtime benchmark."""

    scenario_id: str = ""
    checkpoint_id: str = ""
    snapshot_id: str = ""
    nodes: list[MemoryGraphNode] = Field(default_factory=list)
    edges: list[MemoryGraphEdge] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    generated_at: str | None = None
    source_run_id: str | None = None
    checkpoint_index: int = Field(default=0, ge=0)
    is_terminal: bool = False

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_identity(self) -> RuntimeGraphSnapshotRow:
        for field_name in ("scenario_id", "checkpoint_id", "snapshot_id"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must be non-empty")
        return self


class RuntimeGraphItemRow(FlatArtifactModel):
    """Fields shared by every normalized runtime graph item."""

    scenario_id: NonEmptyString
    runtime_item_id: NonEmptyString
    item_type: Literal["entity", "claim", "relation", "action"]
    lifecycle_state: RecordLifecycleState
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_event_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", validate_default=True)


class RuntimeEntityGraphItemRow(RuntimeGraphItemRow):
    item_type: Literal["entity"] = "entity"
    canonical_name: NonEmptyString
    canonical_id: NonEmptyString
    entity_type: NonEmptyString
    aliases: list[str] = Field(default_factory=list)


class RuntimeClaimGraphItemRow(RuntimeGraphItemRow):
    item_type: Literal["claim"] = "claim"
    claim_id: NonEmptyString
    subject: str = ""
    subject_entity_id: NonEmptyString
    predicate: NonEmptyString
    object: str = ""
    object_entity_id: str = ""
    object_value: str = ""
    scope: str = ""
    valid_from: str = ""
    valid_to: str = ""

    @model_validator(mode="after")
    def validate_claim(self) -> RuntimeClaimGraphItemRow:
        if not self.claim_id.strip():
            raise ValueError("claim graph items must have claim_id")
        if not self.subject_entity_id.strip() or not self.predicate.strip():
            raise ValueError("claim graph items must have subject_entity_id and predicate")
        if not (self.object_entity_id.strip() or self.object_value.strip() or self.object.strip()):
            raise ValueError("claim graph items must have an object")
        return self


class RuntimeRelationType(StrEnum):
    CONTRADICTS = "contradicts"
    SUPERSEDES = "supersedes"
    MERGED_INTO = "merged_into"
    SPLIT_FROM = "split_from"
    REKEYED_FROM = "rekeyed_from"


class RuntimeRelationGraphItemRow(RuntimeGraphItemRow):
    item_type: Literal["relation"] = "relation"
    relation_type: RuntimeRelationType
    source: NonEmptyString
    target: NonEmptyString
    directionality: Literal["directed", "undirected"] = "directed"


class RuntimeActionGraphItemRow(RuntimeGraphItemRow):
    item_type: Literal["action"] = "action"
    action_id: NonEmptyString
    action_type: NonEmptyString
    status: WorkStateStatus
    target_entity_ids: list[str] = Field(default_factory=list)


RuntimeGraphItem: TypeAlias = Annotated[
    RuntimeEntityGraphItemRow | RuntimeClaimGraphItemRow | RuntimeRelationGraphItemRow | RuntimeActionGraphItemRow,
    Field(discriminator="item_type"),
]
RUNTIME_GRAPH_ITEM_ADAPTER = TypeAdapter(RuntimeGraphItem)
RUNTIME_GRAPH_ITEM_TYPES = (
    RuntimeEntityGraphItemRow,
    RuntimeClaimGraphItemRow,
    RuntimeRelationGraphItemRow,
    RuntimeActionGraphItemRow,
)
_PROVIDER_METADATA_KEYS = frozenset({"backend", "provider", "model", "timeout_seconds", "max_retries"})


class GraphItemNormalizationResult(BaseModel):
    """Valid graph items plus classified rows rejected at normalization."""

    items: list[RuntimeGraphItem] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class RuntimeSourceObservationTrace(BaseModel):
    """Sanitized source metadata needed to replay ingestion routing."""

    source_id: str
    source_type: str
    timestamp: str
    modality: str
    trigger_mode: str
    language: str
    task_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class RuntimeGraphDelta(BaseModel):
    """Observable graph mutation produced by one committed extraction."""

    added_nodes: list[MemoryGraphNode] = Field(default_factory=list)
    updated_nodes: list[MemoryGraphNode] = Field(default_factory=list)
    removed_node_ids: list[str] = Field(default_factory=list)
    added_edges: list[MemoryGraphEdge] = Field(default_factory=list)
    updated_edges: list[MemoryGraphEdge] = Field(default_factory=list)
    removed_edge_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", frozen=True)


class RuntimeIngestionTraceRow(BaseModel):
    """Replayable evidence for one source-local extraction and graph mutation."""

    input_source_ids: list[str]
    provider: str
    model: str | None
    requested_model: str | None = None
    actual_model: str | None = None
    prompt_hash: str | None
    extraction_status: ExtractionRunStatus
    provider_attempt_status: ProviderAttemptStatus
    fallback_outcome: FallbackOutcome
    final_output_source: FinalExtractionSource
    failure_code: ExtractionFailureCode | None
    primary_failure_code: ExtractionFailureCode | None
    fallback_provider: str | None
    errors: list[str]
    input_observations: list[RuntimeSourceObservationTrace] = Field(default_factory=list)
    structured_proposal: MemoryExtractionOutput | None = None
    proposed_entities: list[EntityMention] = Field(default_factory=list)
    proposed_claims: list[ExtractedClaim] = Field(default_factory=list)
    proposed_actions: list[ExtractedAction] = Field(default_factory=list)
    proposed_identity_relations: list[ExtractedIdentityRelation] = Field(default_factory=list)
    entity_count: int = Field(default=0, ge=0)
    claim_count: int = Field(default=0, ge=0)
    action_count: int = Field(default=0, ge=0)
    identity_relation_count: int = Field(default=0, ge=0)
    entity_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    action_ids: list[str] = Field(default_factory=list)
    identity_relation_ids: list[str] = Field(default_factory=list)
    language_capability_ids: list[str] = Field(default_factory=list)
    validation_summary: dict[str, int] = Field(default_factory=dict)
    validation_results: dict[str, list[ValidationResult]] = Field(default_factory=dict)
    entity_identity_decisions: list[EntityIdentityDecision] = Field(default_factory=list)
    evolution_result_recorded: bool = False
    compiled_claims: list[ExtractedClaim] = Field(default_factory=list)
    compiled_actions: list[ExtractedAction] = Field(default_factory=list)
    compiled_identity_relations: list[ExtractedIdentityRelation] = Field(default_factory=list)
    lifecycle_transitions: list[ClaimLifecycleTransition] = Field(default_factory=list)
    graph_nodes: list[MemoryGraphNode] = Field(default_factory=list)
    graph_edges: list[MemoryGraphEdge] = Field(default_factory=list)
    graph_validation_errors: list[str] = Field(default_factory=list)
    graph_delta: RuntimeGraphDelta = Field(default_factory=RuntimeGraphDelta)
    operation_id: str | None = None
    operation_status: EvolutionOperationStatus | None = None
    operation_failure_code: EvolutionFailureCategory | None = None
    operation_retryable: bool = False

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_trace_consistency(self) -> RuntimeIngestionTraceRow:
        if (
            len(self.proposed_entities),
            len(self.proposed_claims),
            len(self.proposed_actions),
            len(self.proposed_identity_relations),
        ) != (
            self.entity_count,
            self.claim_count,
            self.action_count,
            self.identity_relation_count,
        ):
            raise ValueError("proposal counts must match proposal rows")
        if (
            [entity.entity_id for entity in self.proposed_entities],
            [claim.claim_id for claim in self.proposed_claims],
            [action.action_id for action in self.proposed_actions],
            [relation.relation_id for relation in self.proposed_identity_relations],
        ) != (
            self.entity_ids,
            self.claim_ids,
            self.action_ids,
            self.identity_relation_ids,
        ):
            raise ValueError("proposal IDs must match proposal rows")
        if [item.source_id for item in self.input_observations] != self.input_source_ids:
            raise ValueError("input observation metadata must match input_source_ids")
        result_fields = (
            self.validation_results,
            self.entity_identity_decisions,
            self.compiled_claims,
            self.compiled_actions,
            self.compiled_identity_relations,
            self.lifecycle_transitions,
            self.graph_nodes,
            self.graph_edges,
            self.graph_validation_errors,
        )
        delta_fields = (
            self.graph_delta.added_nodes,
            self.graph_delta.updated_nodes,
            self.graph_delta.removed_node_ids,
            self.graph_delta.added_edges,
            self.graph_delta.updated_edges,
            self.graph_delta.removed_edge_ids,
        )
        if not self.evolution_result_recorded and (any(result_fields) or any(delta_fields)):
            raise ValueError("unrecorded evolution results cannot contain compiled graph evidence")
        if self.operation_status == EvolutionOperationStatus.COMMITTED and not self.evolution_result_recorded:
            raise ValueError("committed operations require a recorded evolution result")
        _validate_graph_delta(self)
        return self


def _validate_graph_delta(row: RuntimeIngestionTraceRow) -> None:
    node_ids = {node.node_id for node in row.graph_nodes}
    edge_ids = {edge.edge_id for edge in row.graph_edges}
    node_groups = (
        {node.node_id for node in row.graph_delta.added_nodes},
        {node.node_id for node in row.graph_delta.updated_nodes},
        set(row.graph_delta.removed_node_ids),
    )
    edge_groups = (
        {edge.edge_id for edge in row.graph_delta.added_edges},
        {edge.edge_id for edge in row.graph_delta.updated_edges},
        set(row.graph_delta.removed_edge_ids),
    )
    for label, groups in (("node", node_groups), ("edge", edge_groups)):
        if any(left & right for index, left in enumerate(groups) for right in groups[index + 1 :]):
            raise ValueError(f"graph delta {label} operations must be disjoint")
    if not (node_groups[0] | node_groups[1]).issubset(node_ids):
        raise ValueError("added and updated graph nodes must exist in graph_nodes")
    if node_groups[2] & node_ids:
        raise ValueError("removed graph nodes cannot remain in graph_nodes")
    if not (edge_groups[0] | edge_groups[1]).issubset(edge_ids):
        raise ValueError("added and updated graph edges must exist in graph_edges")
    if edge_groups[2] & edge_ids:
        raise ValueError("removed graph edges cannot remain in graph_edges")


@dataclass
class RuntimeSuiteRows:
    scenario_rows: list[SimScenarioResultRow]
    checkpoint_rows: list[RuntimeCheckpointResultRow]
    judge_rows: list[JudgeAggregate]
    llm_rows: list[RuntimeExtractorTraceRow]
    graph_snapshots: list[RuntimeGraphSnapshotRow] = field(default_factory=list)
    graph_items: list[RuntimeGraphItem] = field(default_factory=list)
    alignments: list[RuntimeGraphAlignmentRow] = field(default_factory=list)
    runtime_failures: list[RuntimeCheckpointResultRow] = field(default_factory=list)
    ingestion_traces: list[RuntimeIngestionTraceRow] = field(default_factory=list)
    ingestion_prefix_audits: list[IngestionPrefixAuditRow] = field(default_factory=list)
    effective_mode: str | None = None
    dry_run: bool = False
    provider_metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_row_type("scenario_rows", self.scenario_rows, SimScenarioResultRow)
        _require_row_type("checkpoint_rows", self.checkpoint_rows, RuntimeCheckpointResultRow)
        _require_row_type("judge_rows", self.judge_rows, JudgeAggregate)
        _require_row_type("llm_rows", self.llm_rows, RuntimeExtractorTraceRow)
        _require_row_type("graph_snapshots", self.graph_snapshots, RuntimeGraphSnapshotRow)
        _require_row_types("graph_items", self.graph_items, RUNTIME_GRAPH_ITEM_TYPES)
        _require_row_type("alignments", self.alignments, RuntimeGraphAlignmentRow)
        _require_row_type("runtime_failures", self.runtime_failures, RuntimeCheckpointResultRow)
        _require_row_type("ingestion_traces", self.ingestion_traces, RuntimeIngestionTraceRow)
        from memorii.core.benchmark.memory_evolution_runtime.ingestion_oracle import (
            IngestionPrefixAuditRow,
        )

        _require_row_type(
            "ingestion_prefix_audits",
            self.ingestion_prefix_audits,
            IngestionPrefixAuditRow,
        )
        if any(not key.strip() or not value.strip() for key, value in self.provider_metadata.items()):
            raise ValueError("provider_metadata keys and values must be non-empty")
        unknown_metadata = sorted(set(self.provider_metadata) - _PROVIDER_METADATA_KEYS)
        if unknown_metadata:
            raise ValueError(f"provider_metadata contains unsupported fields: {unknown_metadata}")


def _require_row_type(field_name: str, rows: Sequence[object], row_type: type[T]) -> None:
    invalid = [type(row).__name__ for row in rows if not isinstance(row, row_type)]
    if invalid:
        raise TypeError(f"{field_name} must contain {row_type.__name__} rows, got {invalid}")


def _require_row_types(
    field_name: str,
    rows: Sequence[object],
    row_types: tuple[type[BaseModel], ...],
) -> None:
    invalid = [type(row).__name__ for row in rows if not isinstance(row, row_types)]
    if invalid:
        expected = ", ".join(row_type.__name__ for row_type in row_types)
        raise TypeError(f"{field_name} must contain one of ({expected}), got {invalid}")


@dataclass(frozen=True)
class RuntimeProductionChannels:
    """Public retrieval channels captured before oracle alignment."""

    selected_claim_ids: tuple[str, ...] = ()
    selected_action_ids: tuple[str, ...] = ()
    selected_action_runtime_ids: tuple[str, ...] = ()
    supporting_claim_ids: tuple[str, ...] = ()
    context_claim_ids: tuple[str, ...] = ()
    rejected_claim_ids: tuple[str, ...] = ()
    uncertain_record_ids: tuple[str, ...] = ()


@dataclass
class RuntimeProjection:
    output: SimSystemOutput
    graph_snapshot: MemoryGraphSnapshot
    graph_items: list[RuntimeGraphItem]
    alignments: list[RuntimeGraphAlignment]
    source_id_to_event_id: dict[str, str]
    relation_support: dict[str, str] = field(default_factory=dict)
    action_support: dict[str, str] = field(default_factory=dict)
    action_alignment_rows: list[RuntimeActionAlignmentRow] = field(default_factory=list)
    channel_alignment_rows: list[RuntimeChannelAlignmentRow] = field(default_factory=list)
    production_channels: RuntimeProductionChannels = field(default_factory=RuntimeProductionChannels)
    execution_state: RuntimeExecutionStateSection = field(default_factory=RuntimeExecutionStateSection)
    stage_failure_buckets: list[str] = field(default_factory=list)
    work_state: WorkStateSnapshot | None = None
    retrieval_decision: ProductionRetrievalDecision | None = None
    semantic_comparison: SemanticComparisonResult | None = None

    def __post_init__(self) -> None:
        _require_row_types("graph_items", self.graph_items, RUNTIME_GRAPH_ITEM_TYPES)
        _require_row_type("action_alignment_rows", self.action_alignment_rows, RuntimeActionAlignmentRow)
        _require_row_type("channel_alignment_rows", self.channel_alignment_rows, RuntimeChannelAlignmentRow)
        if not isinstance(self.execution_state, RuntimeExecutionStateSection):
            raise TypeError("execution_state must be a RuntimeExecutionStateSection")
