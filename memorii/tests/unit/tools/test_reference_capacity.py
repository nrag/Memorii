"""Offline checks for the reference workload inputs and sample protocol."""

import hashlib
import json
from datetime import timedelta
from typing import cast
from unittest import TestCase

from tests.support.reference_capacity import (
    CHECKPOINT_TAIL_COUNT,
    COLD_OPERATIONS,
    EVENT_COUNT,
    FIXTURE_START,
    WARM_OPERATIONS,
    Distribution,
    cold_sample_ids,
    event_fill_inputs,
    nearest_rank,
    task_allocations,
    warm_samples,
    workload_manifest,
)


class ReferenceCapacityTests(TestCase):
    def test_fixture_counts_and_graph_edges(self) -> None:
        for distribution in ("balanced", "concentrated"):
            tasks = task_allocations(distribution)
            self.assertEqual(len({task.task_id for task in tasks}), 200)
            self.assertEqual(len({task.solver_id for task in tasks}), 200)
            self.assertEqual(sum(task.execution_nodes for task in tasks), 10_000)
            self.assertEqual(sum(task.solver_nodes for task in tasks), 50_000)
            self.assertEqual(sum(task.sources for task in tasks), 4_096)
            solver_edges = 0
            for task in tasks:
                edges = tuple(task.execution_edges())
                self.assertEqual(len(edges), task.execution_nodes - 1)
                self.assertEqual({source for source, _ in edges}, {f"{task.task_id}:execution:0"})
                self.assertEqual(len({target for _, target in edges}), task.execution_nodes - 1)
                solver_nodes = {f"{task.solver_id}:node:{node}" for node in range(task.solver_nodes)}
                for source, target in task.solver_edges():
                    self.assertTrue(source in solver_nodes and target in solver_nodes)
                    self.assertNotEqual(source, target)
                    solver_edges += 1
            self.assertEqual(solver_edges, 6_250)

        balanced = task_allocations("balanced")
        self.assertEqual({(task.execution_nodes, task.solver_nodes) for task in balanced}, {(50, 250)})
        concentrated = task_allocations("concentrated")
        self.assertEqual((concentrated[0].execution_nodes, concentrated[0].solver_nodes), (5_000, 25_000))
        self.assertEqual([task.execution_nodes for task in concentrated[1:]], [26] * 25 + [25] * 174)
        self.assertEqual([task.solver_nodes for task in concentrated[1:]], [126] * 125 + [125] * 74)
        self.assertEqual([task.sources for task in concentrated], [21] * 96 + [20] * 104)

    def test_coordinates_timestamps_and_source_bodies(self) -> None:
        tasks = task_allocations("concentrated")
        sources = [source for task in tasks for source in task.source_inputs()]
        self.assertEqual(len({source.coordinate for source in sources}), 4_096)
        self.assertEqual([source.timestamp for source in sources], [
            FIXTURE_START + timedelta(seconds=index) for index in range(4_096)
        ])
        for task in tasks:
            observations = tuple(task.observation_inputs())
            self.assertEqual(len(observations), task.sources)
            for index, (node_id, source) in enumerate(observations):
                self.assertEqual(node_id, f"{task.solver_id}:node:{index}")
                self.assertEqual(source.task_id, task.task_id)

        first = sources[0].body()
        self.assertEqual(first, sources[0].body())
        self.assertEqual(len(first), 256 * 1024)
        self.assertTrue(set(first) <= set(b"0123456789abcdef"))
        self.assertEqual(first, hashlib.shake_256(b"reference-capacity:concentrated:source:0\x0017").hexdigest(
            128 * 1024
        ).encode("ascii"))
        self.assertNotEqual(first, sources[1].body())
        self.assertEqual(len(first) * len(sources), 1 << 30)

    def test_event_fill_total_and_checkpoint_boundary(self) -> None:
        mandatory_count = 77_000
        inputs = tuple(event_fill_inputs("balanced", verified_mandatory_events=mandatory_count))
        self.assertEqual(len(inputs) + mandatory_count, EVENT_COUNT)
        self.assertEqual(inputs[0].ordinal, mandatory_count)
        self.assertEqual(inputs[-1].ordinal, EVENT_COUNT - 1)
        self.assertFalse(any(event.checkpoint_tail for event in inputs[:-CHECKPOINT_TAIL_COUNT]))
        for event in inputs[-CHECKPOINT_TAIL_COUNT:]:
            self.assertTrue(event.checkpoint_tail)
            self.assertEqual(event.kind, "status_update")
        first_cycle = inputs[:200]
        self.assertEqual([event.task_id for event in first_cycle], [
            task.task_id for task in task_allocations("balanced")
        ])
        with self.assertRaises(ValueError):
            tuple(event_fill_inputs("balanced", verified_mandatory_events=EVENT_COUNT - CHECKPOINT_TAIL_COUNT + 1))

    def test_sampling_counts_and_target_tasks(self) -> None:
        for operation in WARM_OPERATIONS:
            sequential = tuple(warm_samples("balanced", operation))
            contended = tuple(warm_samples("balanced", operation, contended=True))
            self.assertEqual([sample.measured for sample in sequential], [False] * 20 + [True] * 100)
            self.assertEqual([sample.task_id for sample in sequential], [
                task.task_id for task in task_allocations("balanced")[:120]
            ])
            self.assertEqual([sample.task_id for sample in sequential], [sample.task_id for sample in contended])
            self.assertTrue(all(sample.contended for sample in contended))
            self.assertTrue({sample.operation_id for sample in sequential}.isdisjoint(
                sample.operation_id for sample in contended
            ))
            self.assertEqual(
                {sample.task_id for sample in warm_samples("concentrated", operation)},
                {"reference-capacity:concentrated:task:0"},
            )

        capture_inputs = [
            sample.capture_input()
            for contended in (False, True)
            for sample in warm_samples("balanced", "source_capture", contended=contended)
        ]
        self.assertEqual(len({source.coordinate for source in capture_inputs}), 240)
        fixture_coordinates = {
            source.coordinate for task in task_allocations("balanced") for source in task.source_inputs()
        }
        self.assertTrue(fixture_coordinates.isdisjoint(source.coordinate for source in capture_inputs))
        for operation in COLD_OPERATIONS:
            self.assertEqual(len(set(cold_sample_ids("balanced", operation))), 10)

    def test_manifest_and_quantile_protocol(self) -> None:
        balanced = workload_manifest("balanced")
        self.assertEqual(balanced, workload_manifest("balanced"))
        self.assertNotEqual(balanced, workload_manifest("concentrated"))
        manifest = json.loads(balanced)
        self.assertEqual(len(manifest["warm"]), 720)
        self.assertEqual((manifest["execution_page_max"], manifest["frontier_page_max"]), (32, 16))
        self.assertEqual([nearest_rank(range(10, 0, -1), rank) for rank in (50, 95, 99)], [5, 10, 10])
        self.assertEqual([nearest_rank(range(100, 0, -1), rank) for rank in (50, 95, 99)], [50, 95, 99])
        with self.assertRaises(ValueError):
            task_allocations(cast(Distribution, "unknown"))
        with self.assertRaises(ValueError):
            nearest_rank([0.5, float("nan")], 95)
