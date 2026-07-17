"""Runtime benchmark row and projection models."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.benchmark.artifact_rows import (
    FlatArtifactModel,
    RuntimeActionAlignmentRow,
    RuntimeCheckpointResultRow,
    RuntimeExecutionStateSection,
    RuntimeGraphAlignmentRow,
)
from memorii.core.benchmark.memory_evolution_sim import SimSystemOutput
from memorii.core.calibration.alignment import RuntimeGraphAlignment
from memorii.core.memory_evolution import (
    MemoryGraphEdge,
    MemoryGraphNode,
    MemoryGraphSnapshot,
    ProductionRetrievalDecision,
    WorkStateSnapshot,
)

T = TypeVar("T")


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
    """Typed normalized graph item persisted by the runtime benchmark.

    Projection code intentionally uses plain mappings while it is assembling
    an output. This model is the artifact boundary: a new item field must be
    declared here before it can silently enter alignment reports.
    """

    scenario_id: str = ""
    runtime_item_id: str = ""
    item_type: Literal["entity", "claim", "relation", "action"]
    canonical_name: str = ""
    canonical_id: str = ""
    entity_type: str = ""
    aliases: list[str] = Field(default_factory=list)
    claim_id: str = ""
    subject: str = ""
    subject_entity_id: str = ""
    predicate: str = ""
    object: str = ""
    object_entity_id: str = ""
    object_value: str = ""
    scope: str = ""
    valid_from: str = ""
    valid_to: str = ""
    relation_type: str = ""
    source: str = ""
    target: str = ""
    directionality: Literal["directed", "undirected"] = "directed"
    action_id: str = ""
    action_type: str = ""
    status: str = ""
    target_entity_ids: list[str] = Field(default_factory=list)
    lifecycle_state: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_event_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_identity_and_payload(self) -> RuntimeGraphItemRow:
        for field_name in ("scenario_id", "runtime_item_id", "lifecycle_state"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must be non-empty")
        required_fields: tuple[str, ...]
        if self.item_type == "entity":
            required_fields = ("canonical_id", "canonical_name")
        elif self.item_type == "claim":
            if not self.claim_id.strip():
                raise ValueError("claim graph items must have claim_id")
            if not self.subject_entity_id.strip() or not self.predicate.strip():
                raise ValueError("claim graph items must have subject_entity_id and predicate")
            if not (self.object_entity_id.strip() or self.object_value.strip() or self.object.strip()):
                raise ValueError("claim graph items must have an object")
            required_fields = ()
        elif self.item_type == "relation":
            required_fields = ("relation_type", "source", "target")
        else:
            required_fields = ("action_id", "action_type", "status")
        for field_name in required_fields:
            if not getattr(self, field_name).strip():
                raise ValueError(f"{self.item_type} graph items must have {field_name}")
        return self


@dataclass
class RuntimeSuiteRows:
    scenario_rows: list[dict[str, object]]
    checkpoint_rows: list[RuntimeCheckpointResultRow]
    judge_rows: list[dict[str, object]]
    llm_rows: list[dict[str, object]]
    graph_snapshots: list[RuntimeGraphSnapshotRow] = field(default_factory=list)
    graph_items: list[RuntimeGraphItemRow] = field(default_factory=list)
    alignments: list[RuntimeGraphAlignmentRow] = field(default_factory=list)
    runtime_failures: list[RuntimeCheckpointResultRow] = field(default_factory=list)
    effective_mode: str | None = None
    dry_run: bool = False

    def __post_init__(self) -> None:
        _require_row_type("checkpoint_rows", self.checkpoint_rows, RuntimeCheckpointResultRow)
        _require_row_type("alignments", self.alignments, RuntimeGraphAlignmentRow)
        _require_row_type("runtime_failures", self.runtime_failures, RuntimeCheckpointResultRow)
        self.graph_snapshots = [
            snapshot if isinstance(snapshot, RuntimeGraphSnapshotRow) else RuntimeGraphSnapshotRow.model_validate(snapshot)
            for snapshot in self.graph_snapshots
        ]
        self.graph_items = [
            item if isinstance(item, RuntimeGraphItemRow) else RuntimeGraphItemRow.model_validate(item)
            for item in self.graph_items
        ]


def _require_row_type(field_name: str, rows: Sequence[object], row_type: type[T]) -> None:
    invalid = [type(row).__name__ for row in rows if not isinstance(row, row_type)]
    if invalid:
        raise TypeError(f"{field_name} must contain {row_type.__name__} rows, got {invalid}")

@dataclass
class RuntimeProjection:
    output: SimSystemOutput
    graph_snapshot: MemoryGraphSnapshot
    graph_items: Sequence[RuntimeGraphItemRow | Mapping[str, object]]
    alignments: list[RuntimeGraphAlignment]
    source_id_to_event_id: dict[str, str]
    relation_support: dict[str, str] = field(default_factory=dict)
    action_support: dict[str, str] = field(default_factory=dict)
    action_alignment_rows: list[RuntimeActionAlignmentRow] = field(default_factory=list)
    execution_state: RuntimeExecutionStateSection = field(default_factory=RuntimeExecutionStateSection)
    stage_failure_buckets: list[str] = field(default_factory=list)
    work_state: WorkStateSnapshot | None = None
    retrieval_decision: ProductionRetrievalDecision | None = None

    def __post_init__(self) -> None:
        self.graph_items = [
            item if isinstance(item, RuntimeGraphItemRow) else RuntimeGraphItemRow.model_validate(item)
            for item in self.graph_items
        ]
        self.action_alignment_rows = [
            row if isinstance(row, RuntimeActionAlignmentRow) else RuntimeActionAlignmentRow.from_runtime_alignment(row)
            for row in self.action_alignment_rows
        ]
        if not isinstance(self.execution_state, RuntimeExecutionStateSection):
            self.execution_state = RuntimeExecutionStateSection.model_validate(self.execution_state)
