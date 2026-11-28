"""Deterministic inputs for the release reference workload.

This module plans logical inputs. It does not seed a production store or
measure capacity. The installed runner must verify persisted closure and
derive its artifact manifest from the actual owner publications.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

Distribution = Literal["balanced", "concentrated"]
WarmOperation = Literal["state_read", "source_capture", "command_commit"]
ColdOperation = Literal["startup_acquisition", "checkpoint_resume", "backup_pause"]

TASK_COUNT = 200
EXECUTION_NODE_COUNT = 10_000
SOLVER_NODE_COUNT = 50_000
SOURCE_COUNT = 4_096
SOURCE_BODY_BYTES = 256 * 1024
SOURCE_SEED = 17
EVENT_COUNT = 100_000
CHECKPOINT_TAIL_COUNT = 1_000
WARMUP_COUNT = 20
WARM_SAMPLE_COUNT = 100
COLD_SAMPLE_COUNT = 10
EXECUTION_PAGE_MAX = 32
FRONTIER_PAGE_MAX = 16
FIXTURE_START = datetime(2025, 1, 1, tzinfo=UTC)
WARM_OPERATIONS: tuple[WarmOperation, ...] = ("state_read", "source_capture", "command_commit")
COLD_OPERATIONS: tuple[ColdOperation, ...] = ("startup_acquisition", "checkpoint_resume", "backup_pause")


@dataclass(frozen=True)
class SourceInput:
    coordinate: str
    task_id: str
    timestamp: datetime

    def body(self) -> bytes:
        """Generate exactly one body at a time, with no shared RNG state."""
        material = f"{self.coordinate}\0{SOURCE_SEED}".encode("ascii")
        return hashlib.shake_256(material).hexdigest(SOURCE_BODY_BYTES // 2).encode("ascii")


@dataclass(frozen=True)
class TaskAllocation:
    distribution: Distribution
    index: int
    execution_nodes: int
    solver_nodes: int
    first_solver_node: int
    first_source: int
    sources: int

    @property
    def task_id(self) -> str:
        return f"reference-capacity:{self.distribution}:task:{self.index}"

    @property
    def solver_id(self) -> str:
        return f"{self.task_id}:solver"

    def execution_edges(self) -> Iterator[tuple[str, str]]:
        root = f"{self.task_id}:execution:0"
        for node in range(1, self.execution_nodes):
            yield root, f"{self.task_id}:execution:{node}"

    def solver_edges(self) -> Iterator[tuple[str, str]]:
        # Every eighth global node starts one edge, but its endpoint stays
        # within this run even when the corresponding block crosses tasks.
        for node in range(-self.first_solver_node % 8, self.solver_nodes, 8):
            yield (
                f"{self.solver_id}:node:{node}",
                f"{self.solver_id}:node:{(node + 1) % self.solver_nodes}",
            )

    def source_inputs(self) -> Iterator[SourceInput]:
        for index in range(self.first_source, self.first_source + self.sources):
            yield SourceInput(
                coordinate=f"reference-capacity:{self.distribution}:source:{index}",
                task_id=self.task_id,
                timestamp=FIXTURE_START + timedelta(seconds=index),
            )

    def observation_inputs(self) -> Iterator[tuple[str, SourceInput]]:
        for node, source in enumerate(self.source_inputs()):
            if node >= self.solver_nodes:
                return
            yield f"{self.solver_id}:node:{node}", source


def _distributed_count(total: int, concentrated_first: int, index: int, distribution: Distribution) -> int:
    if distribution == "balanced":
        return total // TASK_COUNT
    if index == 0:
        return concentrated_first
    quotient, remainder = divmod(total - concentrated_first, TASK_COUNT - 1)
    return quotient + int(index <= remainder)


def task_allocations(distribution: Distribution) -> tuple[TaskAllocation, ...]:
    if distribution not in ("balanced", "concentrated"):
        raise ValueError(f"unknown reference distribution: {distribution}")
    first_solver_node = first_source = 0
    tasks = []
    for index in range(TASK_COUNT):
        solver_nodes = _distributed_count(SOLVER_NODE_COUNT, 25_000, index, distribution)
        sources = 20 + int(index < 96)
        tasks.append(
            TaskAllocation(
                distribution=distribution,
                index=index,
                execution_nodes=_distributed_count(EXECUTION_NODE_COUNT, 5_000, index, distribution),
                solver_nodes=solver_nodes,
                first_solver_node=first_solver_node,
                first_source=first_source,
                sources=sources,
            )
        )
        first_source += sources
        first_solver_node += solver_nodes
    return tuple(tasks)


@dataclass(frozen=True)
class EventFillInput:
    ordinal: int
    task_id: str
    timestamp: datetime
    kind: Literal["status_update", "overlay_update"]
    checkpoint_tail: bool


def event_fill_inputs(
    distribution: Distribution,
    *,
    verified_mandatory_events: int,
) -> Iterator[EventFillInput]:
    """Plan filler after the runner attests its actual setup event count.

    The last 1,000 inputs are individual status batches after the checkpoint
    boundary. The signed writer still owns each record's monotonic version.
    """
    if not 0 <= verified_mandatory_events <= EVENT_COUNT - CHECKPOINT_TAIL_COUNT:
        raise ValueError("mandatory runtime events leave no valid checkpoint tail")
    tasks = task_allocations(distribution)
    for index in range(verified_mandatory_events, EVENT_COUNT):
        tail = index >= EVENT_COUNT - CHECKPOINT_TAIL_COUNT
        task = tasks[(index - verified_mandatory_events) % TASK_COUNT]
        yield EventFillInput(
            ordinal=index,
            task_id=task.task_id,
            timestamp=FIXTURE_START + timedelta(seconds=index),
            kind="status_update" if tail or index // TASK_COUNT % 2 == 0 else "overlay_update",
            checkpoint_tail=tail,
        )


@dataclass(frozen=True)
class WarmSample:
    ordinal: int
    operation: WarmOperation
    operation_id: str
    task_id: str
    measured: bool
    contended: bool

    def capture_input(self) -> SourceInput:
        if self.operation != "source_capture":
            raise ValueError("source input requires a capture sample")
        return SourceInput(
            coordinate=f"{self.operation_id}:source",
            task_id=self.task_id,
            timestamp=FIXTURE_START + timedelta(seconds=SOURCE_COUNT + self.ordinal),
        )


def warm_samples(
    distribution: Distribution,
    operation: WarmOperation,
    *,
    contended: bool = False,
) -> Iterator[WarmSample]:
    if operation not in WARM_OPERATIONS:
        raise ValueError(f"unknown warm operation: {operation}")
    tasks = task_allocations(distribution)
    run = "contended" if contended else "sequential"
    for index in range(WARMUP_COUNT + WARM_SAMPLE_COUNT):
        task = tasks[index % TASK_COUNT if distribution == "balanced" else 0]
        yield WarmSample(
            ordinal=index,
            operation=operation,
            operation_id=f"reference-capacity:{distribution}:{run}:{operation}:{index}",
            task_id=task.task_id,
            measured=index >= WARMUP_COUNT,
            contended=contended,
        )


def cold_sample_ids(distribution: Distribution, operation: ColdOperation) -> tuple[str, ...]:
    if distribution not in ("balanced", "concentrated"):
        raise ValueError(f"unknown reference distribution: {distribution}")
    if operation not in COLD_OPERATIONS:
        raise ValueError(f"unknown cold operation: {operation}")
    return tuple(f"reference-capacity:{distribution}:cold:{operation}:{index}" for index in range(COLD_SAMPLE_COUNT))


def nearest_rank(samples: Sequence[float], percentile: int) -> float:
    """Use all elapsed samples. Callers must account for failures separately."""
    if not samples or not 1 <= percentile <= 100 or any(not math.isfinite(x) or x < 0 for x in samples):
        raise ValueError("percentiles require finite nonnegative samples and a rank from 1 to 100")
    return sorted(samples)[(percentile * len(samples) + 99) // 100 - 1]


def workload_manifest(distribution: Distribution) -> bytes:
    """Serialize ordered workload inputs, not an attestation of stored data."""
    plan = {
        "tasks": [asdict(task) for task in task_allocations(distribution)],
        "source_seed": SOURCE_SEED,
        "source_body_bytes": SOURCE_BODY_BYTES,
        "fixture_start": FIXTURE_START.isoformat(),
        "event_count": EVENT_COUNT,
        "checkpoint_tail_count": CHECKPOINT_TAIL_COUNT,
        "execution_page_max": EXECUTION_PAGE_MAX,
        "frontier_page_max": FRONTIER_PAGE_MAX,
        "warm": [
            asdict(sample)
            for contended in (False, True)
            for operation in WARM_OPERATIONS
            for sample in warm_samples(distribution, operation, contended=contended)
        ],
        "cold": {operation: cold_sample_ids(distribution, operation) for operation in COLD_OPERATIONS},
    }
    return json.dumps(plan, sort_keys=True, separators=(",", ":")).encode("ascii")
