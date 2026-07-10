from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

from memorii.core.benchmark.hotpotqa import (
    build_hotpotqa_benchmark_fixtures,
    build_hotpotqa_fixtures,
    load_hotpotqa_examples,
    run_hotpotqa_benchmark,
    select_hotpotqa_subset,
)
from memorii.core.benchmark.models import BenchmarkScenarioType

HOTSPOT_FIXTURE_PATH = files("memorii.core.benchmark.fixture_sets").joinpath("hotpotqa_sample.json")


def test_hotpotqa_adapter_parses_json_and_jsonl(tmp_path: Path) -> None:
    source = HOTSPOT_FIXTURE_PATH
    examples = load_hotpotqa_examples(source, split="validation")
    assert len(examples) == 3
    assert examples[0].example_id == "hp1"

    jsonl_path = tmp_path / "hotpotqa_sample.jsonl"
    rows = json.loads(source.read_text(encoding="utf-8"))["validation"]
    jsonl_path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    jsonl_examples = load_hotpotqa_examples(jsonl_path)
    assert [item.example_id for item in jsonl_examples] == [item.example_id for item in examples]


def test_hotpotqa_subset_selection_is_deterministic() -> None:
    source = HOTSPOT_FIXTURE_PATH
    examples = load_hotpotqa_examples(source, split="validation")
    subset_a = select_hotpotqa_subset(
        examples,
        dataset_source=str(source),
        split="validation",
        seed=123,
        subset_size=2,
        question_type="comparison",
    )
    subset_b = select_hotpotqa_subset(
        examples,
        dataset_source=str(source),
        split="validation",
        seed=123,
        subset_size=2,
        question_type="comparison",
    )
    assert [item.example_id for item in subset_a] == [item.example_id for item in subset_b]


def test_hotpotqa_fixture_transform_and_harness_run(tmp_path: Path) -> None:
    source = HOTSPOT_FIXTURE_PATH
    examples = load_hotpotqa_examples(source, split="validation")
    subset = select_hotpotqa_subset(
        examples,
        dataset_source=str(source),
        split="validation",
        seed=7,
        subset_size=2,
    )
    fixtures = build_hotpotqa_fixtures(subset)
    categories = {fixture.category for fixture in fixtures}
    assert BenchmarkScenarioType.SEMANTIC_RETRIEVAL in categories
    assert BenchmarkScenarioType.IMPLICIT_RECALL in categories
    assert BenchmarkScenarioType.END_TO_END in categories

    report, run_dir = run_hotpotqa_benchmark(
        dataset_path=source,
        split="validation",
        seed=7,
        subset_size=2,
        output_root=str(tmp_path / "artifacts" / "benchmarks"),
    )
    assert report.baseline_comparison
    assert (run_dir / "report.json").exists()
    assert (run_dir / "baseline.json").exists()
    assert (run_dir / "hotpotqa_metadata.json").exists()


def test_hotpotqa_benchmark_fixture_builder_records_selection_metadata() -> None:
    source = HOTSPOT_FIXTURE_PATH

    fixtures, metadata = build_hotpotqa_benchmark_fixtures(
        dataset_path=source,
        split="validation",
        seed=7,
        subset_size=2,
        question_type="comparison",
    )

    assert fixtures
    assert metadata.dataset_path == str(source)
    assert metadata.split == "validation"
    assert metadata.subset_size_requested == 2
    assert metadata.question_type == "comparison"
    assert metadata.selected_example_ids
    assert metadata.fixture_count == len(fixtures)
