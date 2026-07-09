"""Runtime benchmark row and projection models."""

from __future__ import annotations

from dataclasses import dataclass, field

from memorii.core.calibration.alignment import RuntimeGraphAlignment
from memorii.core.benchmark.memory_evolution_sim import SimSystemOutput
from memorii.core.memory_evolution import MemoryGraphSnapshot


@dataclass
class RuntimeSuiteRows:
    scenario_rows: list[dict[str, object]]
    checkpoint_rows: list[dict[str, object]]
    judge_rows: list[dict[str, object]]
    llm_rows: list[dict[str, object]]
    graph_snapshots: list[dict[str, object]] = field(default_factory=list)
    graph_items: list[dict[str, object]] = field(default_factory=list)
    alignments: list[dict[str, object]] = field(default_factory=list)
    runtime_failures: list[dict[str, object]] = field(default_factory=list)

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
