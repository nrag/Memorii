"""Fixture loaders for fixture-backed benchmark suites."""

from __future__ import annotations

import argparse

from memorii.core.benchmark.fixture_sets.benchmark_minimal import load_benchmark_fixture_set
from memorii.core.benchmark.fixture_sets.memory_lifecycle_v1 import load_memory_lifecycle_v1_fixture_set
from memorii.core.benchmark.fixture_sets.retrieval_corruption_v1 import load_retrieval_corruption_v1_fixture_set
from memorii.core.benchmark.hotpotqa import build_hotpotqa_benchmark_fixtures
from memorii.core.benchmark.models import BenchmarkScenarioFixture


def load_memory_lifecycle_fixture_set(
    _args: argparse.Namespace,
) -> tuple[list[BenchmarkScenarioFixture], str, dict[str, object] | None]:
    return (
        load_memory_lifecycle_v1_fixture_set(),
        "memorii.core.benchmark.fixture_sets.memory_lifecycle_v1",
        None,
    )


def load_retrieval_corruption_fixture_set(
    _args: argparse.Namespace,
) -> tuple[list[BenchmarkScenarioFixture], str, dict[str, object] | None]:
    return (
        load_retrieval_corruption_v1_fixture_set(),
        "memorii.core.benchmark.fixture_sets.retrieval_corruption_v1",
        None,
    )


def load_minimal_fixture_set(
    _args: argparse.Namespace,
) -> tuple[list[BenchmarkScenarioFixture], str, dict[str, object] | None]:
    return (
        load_benchmark_fixture_set(),
        "memorii.core.benchmark.fixture_sets.benchmark_minimal",
        None,
    )


def load_hotpotqa_v1_fixture_set(
    args: argparse.Namespace,
) -> tuple[list[BenchmarkScenarioFixture], str, dict[str, object] | None]:
    fixtures, metadata = build_hotpotqa_benchmark_fixtures(
        dataset_path=args.hotpotqa_dataset,
        split=args.hotpotqa_split,
        seed=args.seed,
        subset_size=args.hotpotqa_subset_size,
        question_type=args.hotpotqa_question_type,
    )
    return fixtures, str(args.hotpotqa_dataset), metadata.model_dump(mode="json")
