from pathlib import Path

import pytest
from memorii.core.benchmark import reproducibility
from memorii.core.benchmark.fixture_sets.benchmark_minimal import load_benchmark_fixture_set
from memorii.core.benchmark.harness import BenchmarkHarness
from memorii.core.benchmark.models import BenchmarkRunConfig
from memorii.core.benchmark.reproducibility import (
    build_source_tree_fingerprint,
    resolve_source_revision,
    resolve_source_state,
)


def test_source_tree_fingerprint_is_content_addressed(tmp_path: Path) -> None:
    source = tmp_path / "owned"
    source.mkdir()
    module = source / "module.py"
    module.write_text("VALUE = 1\n", encoding="utf-8")

    before = build_source_tree_fingerprint(root=tmp_path, relative_paths=["owned"])
    module.write_text("VALUE = 2\n", encoding="utf-8")
    after = build_source_tree_fingerprint(root=tmp_path, relative_paths=["owned"])

    assert before != after


def test_live_source_revision_fails_closed_without_revision_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MEMORII_SOURCE_REVISION", raising=False)

    with pytest.raises(ValueError, match="live benchmark reports require"):
        resolve_source_revision(root=tmp_path, dry_run=False)

    assert resolve_source_revision(root=tmp_path, dry_run=True) == "local-source-tree"


def test_source_revision_environment_value_must_be_normalized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEMORII_SOURCE_REVISION", " revision:test ")

    with pytest.raises(ValueError, match="non-empty and normalized"):
        resolve_source_revision(root=tmp_path, dry_run=False)


def test_source_state_distinguishes_clean_dirty_and_unversioned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reproducibility, "_git_status_porcelain", lambda _root: "")
    assert resolve_source_state(root=tmp_path) == "clean"

    monkeypatch.setattr(
        reproducibility,
        "_git_status_porcelain",
        lambda _root: " M memorii/core/runtime.py",
    )
    assert resolve_source_state(root=tmp_path) == "dirty"

    monkeypatch.setattr(reproducibility, "_git_status_porcelain", lambda _root: None)
    assert resolve_source_state(root=tmp_path) == "unversioned"


def test_run_id_is_stable_for_same_config_and_fixtures() -> None:
    fixtures = load_benchmark_fixture_set()
    config = BenchmarkRunConfig(seed=99, run_label="stable")
    harness = BenchmarkHarness()

    report1 = harness.run(fixtures=fixtures, config=config)
    report2 = harness.run(fixtures=fixtures, config=config)

    assert report1.run_id == report2.run_id


def test_seed_changes_run_id() -> None:
    fixtures = load_benchmark_fixture_set()
    harness = BenchmarkHarness()

    report1 = harness.run(fixtures=fixtures, config=BenchmarkRunConfig(seed=1, run_label="stable"))
    report2 = harness.run(fixtures=fixtures, config=BenchmarkRunConfig(seed=2, run_label="stable"))

    assert report1.run_id != report2.run_id


def test_reproducible_scenario_outputs_for_same_seed() -> None:
    fixtures = load_benchmark_fixture_set()
    harness = BenchmarkHarness()
    config = BenchmarkRunConfig(seed=7, run_label="benchmark_eval")

    report1 = harness.run(fixtures=fixtures, config=config)
    report2 = harness.run(fixtures=fixtures, config=config)

    fingerprint1 = [
        (item.scenario_id, item.system.value, item.metrics.model_dump(exclude_none=True))
        for item in sorted(report1.scenario_results, key=lambda r: (r.scenario_id, r.system.value))
    ]
    fingerprint2 = [
        (item.scenario_id, item.system.value, item.metrics.model_dump(exclude_none=True))
        for item in sorted(report2.scenario_results, key=lambda r: (r.scenario_id, r.system.value))
    ]
    assert fingerprint1 == fingerprint2
