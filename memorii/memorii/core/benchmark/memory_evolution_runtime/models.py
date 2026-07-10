"""Runtime benchmark row and projection models."""

from __future__ import annotations

from dataclasses import dataclass, field

from memorii.core.benchmark.artifact_rows import RuntimeCheckpointResultRow, RuntimeGraphAlignmentRow
from memorii.core.calibration.alignment import RuntimeGraphAlignment
from memorii.core.benchmark.memory_evolution_sim import SimSystemOutput
from memorii.core.memory_evolution import MemoryGraphSnapshot


@dataclass
class RuntimeSuiteRows:
    scenario_rows: list[dict[str, object]]
    checkpoint_rows: list[RuntimeCheckpointResultRow]
    judge_rows: list[dict[str, object]]
    llm_rows: list[dict[str, object]]
    graph_snapshots: list[dict[str, object]] = field(default_factory=list)
    graph_items: list[dict[str, object]] = field(default_factory=list)
    alignments: list[RuntimeGraphAlignmentRow] = field(default_factory=list)
    runtime_failures: list[RuntimeCheckpointResultRow] = field(default_factory=list)

    def __post_init__(self) -> None:
        _require_row_type("checkpoint_rows", self.checkpoint_rows, RuntimeCheckpointResultRow)
        _require_row_type("alignments", self.alignments, RuntimeGraphAlignmentRow)
        _require_row_type("runtime_failures", self.runtime_failures, RuntimeCheckpointResultRow)


def _require_row_type[T](field_name: str, rows: list[object], row_type: type[T]) -> None:
    invalid = [type(row).__name__ for row in rows if not isinstance(row, row_type)]
    if invalid:
        raise TypeError(f"{field_name} must contain {row_type.__name__} rows, got {invalid}")

@dataclass
class RuntimeProjection:
    output: SimSystemOutput
    graph_snapshot: MemoryGraphSnapshot
    graph_items: list[dict[str, object]]
    alignments: list[RuntimeGraphAlignment]
    source_id_to_event_id: dict[str, str]
    relation_support: dict[str, str] = field(default_factory=dict)
    action_support: dict[str, str] = field(default_factory=dict)
    action_alignment_rows: list[dict[str, object]] = field(default_factory=list)
    execution_state: dict[str, object] = field(default_factory=dict)
    stage_failure_buckets: list[str] = field(default_factory=list)
