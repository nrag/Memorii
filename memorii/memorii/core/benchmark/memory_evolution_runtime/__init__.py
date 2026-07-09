"""Public facade for runtime-backed memory evolution benchmark helpers."""

from memorii.core.benchmark.memory_evolution_runtime.alignment import align_runtime_graph_to_oracle
from memorii.core.benchmark.memory_evolution_runtime.artifacts import (
    runtime_alignment_summary,
    runtime_graph_completeness_metrics,
    runtime_summary_metrics,
    runtime_warning_policy,
    write_runtime_artifacts,
)
from memorii.core.benchmark.memory_evolution_runtime.checkpoint_projection import (
    project_runtime_checkpoint,
    runtime_failure_buckets,
)
from memorii.core.benchmark.memory_evolution_runtime.models import RuntimeProjection, RuntimeSuiteRows
from memorii.core.benchmark.memory_evolution_runtime.graph_items import graph_items_from_snapshot
from memorii.core.benchmark.memory_evolution_runtime.ingestion import ingest_scenario_surface_observations
from memorii.core.benchmark.memory_evolution_runtime.execution_state_projection import (
    _expected_action_alignment_rows,
    normalize_action_status,
)
from memorii.core.benchmark.memory_evolution_runtime.runner import (
    OracleVisibleMemoryExtractor,
    RecordingMemoryExtractor,
    build_runtime_extractor,
    extractor_fallback_count,
    extractor_trace_rows,
    run_runtime_scenarios,
    runtime_final_output_source,
    validate_runtime_live_safety,
)

__all__ = [
    "OracleVisibleMemoryExtractor",
    "RecordingMemoryExtractor",
    "RuntimeProjection",
    "RuntimeSuiteRows",
    "_expected_action_alignment_rows",
    "align_runtime_graph_to_oracle",
    "build_runtime_extractor",
    "extractor_fallback_count",
    "extractor_trace_rows",
    "graph_items_from_snapshot",
    "ingest_scenario_surface_observations",
    "normalize_action_status",
    "project_runtime_checkpoint",
    "run_runtime_scenarios",
    "runtime_alignment_summary",
    "runtime_failure_buckets",
    "runtime_final_output_source",
    "runtime_graph_completeness_metrics",
    "runtime_summary_metrics",
    "runtime_warning_policy",
    "validate_runtime_live_safety",
    "write_runtime_artifacts",
]
