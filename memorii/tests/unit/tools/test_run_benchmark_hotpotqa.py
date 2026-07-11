from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

import pytest

from memorii.tools.run_benchmark import main
from tests.unit.tools.run_benchmark_test_helpers import (
    _latest_run_dir,
    _summary_fields,
)

HOTPOTQA_SAMPLE_PATH = files("memorii.core.benchmark.fixture_sets").joinpath("hotpotqa_sample.json")


def test_hotpotqa_benchmark_cli_runs_and_writes_metadata(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    assert main(
        [
            "--suite",
            "hotpotqa_v1",
            "--storage-root",
            str(tmp_path),
            "--hotpotqa-dataset",
            str(HOTPOTQA_SAMPLE_PATH),
            "--hotpotqa-subset-size",
            "2",
        ]
    ) == 0

    output = capsys.readouterr().out
    run_dir = _latest_run_dir(tmp_path, "hotpotqa_v1")
    payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    metadata = json.loads((run_dir / "hotpotqa_metadata.json").read_text(encoding="utf-8"))
    fields = _summary_fields(output)

    assert fields["suite"] == "hotpotqa_v1"
    assert fields["mode"] == "auto"
    assert int(fields["scenarios"]) == payload["summary"]["scenario_fixtures_total"]
    assert int(fields["memorii_runs"]) == payload["summary"]["memorii_runs_total"]
    assert int(fields["llm_calls"]) == 0
    assert metadata["dataset_path"] == str(HOTPOTQA_SAMPLE_PATH)
    assert metadata["subset_size_requested"] == 2
    assert metadata["selected_example_ids"]


def test_hotpotqa_benchmark_uses_package_default_dataset(
    tmp_path: Path,
) -> None:
    assert main(
        [
            "--suite",
            "hotpotqa_v1",
            "--storage-root",
            str(tmp_path),
            "--hotpotqa-subset-size",
            "1",
        ]
    ) == 0

    run_dir = _latest_run_dir(tmp_path, "hotpotqa_v1")
    metadata = json.loads((run_dir / "hotpotqa_metadata.json").read_text(encoding="utf-8"))
    assert metadata["dataset_path"].endswith("hotpotqa_sample.json")
    assert metadata["selected_example_ids"]


def test_hotpotqa_benchmark_question_type_filter(
    tmp_path: Path,
) -> None:
    assert main(
        [
            "--suite",
            "hotpotqa_v1",
            "--storage-root",
            str(tmp_path),
            "--hotpotqa-dataset",
            str(HOTPOTQA_SAMPLE_PATH),
            "--hotpotqa-question-type",
            "bridge",
        ]
    ) == 0

    run_dir = _latest_run_dir(tmp_path, "hotpotqa_v1")
    metadata = json.loads((run_dir / "hotpotqa_metadata.json").read_text(encoding="utf-8"))
    assert metadata["question_type"] == "bridge"
    assert metadata["selected_example_ids"] == ["hp2"]


def test_hotpotqa_benchmark_rejects_llm_modes() -> None:
    with pytest.raises(SystemExit, match="deterministic modes"):
        main(["--suite", "hotpotqa_v1", "--mode", "llm"])
