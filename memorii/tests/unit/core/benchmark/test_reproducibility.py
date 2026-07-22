from pathlib import Path

import pytest
from memorii.core.benchmark import reproducibility
from memorii.core.benchmark.fixture_sets.benchmark_minimal import load_benchmark_fixture_set
from memorii.core.benchmark.harness import BenchmarkHarness
from memorii.core.benchmark.models import BenchmarkRunConfig
from memorii.core.benchmark.reproducibility import (
    build_installable_package_fingerprint,
    resolve_source_identity,
    resolve_source_revision,
    resolve_source_state,
)


def test_installable_package_fingerprint_is_content_addressed(tmp_path: Path) -> None:
    package = tmp_path / "memorii"
    package.mkdir()
    module = package / "module.py"
    module.write_text("VALUE = 1\n", encoding="utf-8")

    before = build_installable_package_fingerprint(package_root=package)
    module.write_text("VALUE = 2\n", encoding="utf-8")
    after = build_installable_package_fingerprint(package_root=package)

    assert before != after


@pytest.mark.parametrize("mutation", ["change", "add", "remove", "rename"])
def test_installable_package_fingerprint_observes_every_tree_mutation(
    tmp_path: Path,
    mutation: str,
) -> None:
    package = tmp_path / "memorii"
    package.mkdir()
    (package / "entry.py").write_text("from memorii import target\n", encoding="utf-8")
    target = package / "target.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    before = build_installable_package_fingerprint(package_root=package)

    if mutation == "change":
        target.write_text("VALUE = 2\n", encoding="utf-8")
    elif mutation == "add":
        (package / "added.json").write_text('{"value": 2}\n', encoding="utf-8")
    elif mutation == "remove":
        target.unlink()
    else:
        target.rename(package / "renamed.py")

    after = build_installable_package_fingerprint(package_root=package)
    assert after != before


def test_installable_package_fingerprint_ignores_outside_files(tmp_path: Path) -> None:
    package = tmp_path / "memorii"
    package.mkdir()
    (package / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("before\n", encoding="utf-8")

    before = build_installable_package_fingerprint(package_root=package)
    outside.write_text("after\n", encoding="utf-8")
    after = build_installable_package_fingerprint(package_root=package)

    assert after == before


def test_installable_package_fingerprint_is_independent_of_creation_order(tmp_path: Path) -> None:
    first = tmp_path / "first" / "memorii"
    second = tmp_path / "second" / "memorii"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    contents = {"a.bin": b"\x00\xff\n", "z.py": b"VALUE = 1\n"}
    for name, content in contents.items():
        (first / name).write_bytes(content)
    for name, content in reversed(tuple(contents.items())):
        (second / name).write_bytes(content)

    assert build_installable_package_fingerprint(
        package_root=first
    ) == build_installable_package_fingerprint(package_root=second)


def test_installable_package_fingerprint_excludes_generated_bytecode(tmp_path: Path) -> None:
    package = tmp_path / "memorii"
    cache = package / "__pycache__"
    cache.mkdir(parents=True)
    (package / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    bytecode = cache / "module.pyc"
    optimized = package / "module.pyo"
    bytecode.write_bytes(b"before")
    optimized.write_bytes(b"before")

    before = build_installable_package_fingerprint(package_root=package)
    bytecode.write_bytes(b"after")
    optimized.write_bytes(b"after")
    after = build_installable_package_fingerprint(package_root=package)

    assert after == before


def test_installable_package_fingerprint_fails_closed_when_root_does_not_exist(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_installable_package_fingerprint(package_root=tmp_path / "missing-root")


def test_installable_package_fingerprint_fails_closed_on_empty_directories(tmp_path: Path) -> None:
    package = tmp_path / "memorii"
    package.mkdir()

    with pytest.raises(ValueError, match="contains no owned source files"):
        build_installable_package_fingerprint(package_root=package)


def test_installable_package_fingerprint_fails_closed_on_nested_symlinks(tmp_path: Path) -> None:
    package = tmp_path / "memorii"
    package.mkdir()
    target = tmp_path / "target.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    (package / "linked.py").symlink_to(target)

    with pytest.raises(ValueError, match="cannot contain symlinks"):
        build_installable_package_fingerprint(package_root=package)


def test_installable_package_fingerprint_fails_closed_on_symlinked_root(tmp_path: Path) -> None:
    package = tmp_path / "memorii"
    package.mkdir()
    (package / "source.py").write_text("VALUE = 1\n", encoding="utf-8")
    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(package, target_is_directory=True)

    with pytest.raises(ValueError, match="root cannot be a symlink"):
        build_installable_package_fingerprint(package_root=linked_root)


def test_installable_package_fingerprint_propagates_read_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = tmp_path / "memorii"
    package.mkdir()
    source = package / "source.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    original_read_bytes = Path.read_bytes

    def fail_for_owned_source(path: Path) -> bytes:
        if path == source.resolve():
            raise OSError("cannot read owned source")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fail_for_owned_source)

    with pytest.raises(OSError, match="cannot read owned source"):
        build_installable_package_fingerprint(package_root=package)


@pytest.mark.parametrize(
    "entry_source",
    [
        "from importlib import import_module\n(load,) = (import_module,)\nMODULE = load('memorii.dependency')\n",
        "import importlib\nload = getattr(importlib, 'import_module')\nMODULE = load('memorii.dependency')\n",
    ],
)
def test_installable_package_fingerprint_covers_adversarial_dynamic_import_targets(
    tmp_path: Path,
    entry_source: str,
) -> None:
    package = tmp_path / "memorii"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "entry.py").write_text(entry_source, encoding="utf-8")
    dependency = package / "dependency.py"
    dependency.write_text("VALUE = 1\n", encoding="utf-8")

    before = build_installable_package_fingerprint(package_root=package)
    dependency.write_text("VALUE = 2\n", encoding="utf-8")
    after = build_installable_package_fingerprint(package_root=package)

    assert after != before


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


def test_source_revision_environment_cannot_spoof_checked_out_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reproducibility, "_git_head_revision", lambda _root: "a" * 40)
    monkeypatch.setenv("MEMORII_SOURCE_REVISION", "b" * 40)

    with pytest.raises(ValueError, match="does not match"):
        resolve_source_revision(root=tmp_path, dry_run=False)


def test_source_identity_certifies_only_clean_versioned_trees(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reproducibility, "_git_head_revision", lambda _root: "a" * 40)
    monkeypatch.setattr(reproducibility, "_git_status_porcelain", lambda _root: "")
    identity = resolve_source_identity(root=tmp_path, dry_run=False)
    assert identity.revision == "a" * 40
    assert identity.state == "clean"
    assert identity.certifiable is True


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
