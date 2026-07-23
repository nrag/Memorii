from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "memorii"
FINGERPRINT_FIELDS = (
    "fixture_fingerprint",
    "evaluation_fingerprint",
    "system_fingerprint",
)


def _copy_package(destination: Path, *, reverse: bool = False) -> Path:
    package = destination / "memorii"
    package.mkdir(parents=True)
    paths = sorted(
        (
            path
            for path in PACKAGE_ROOT.rglob("*")
            if "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}
        ),
        key=lambda path: path.relative_to(PACKAGE_ROOT).as_posix(),
        reverse=reverse,
    )
    for source in paths:
        relative = source.relative_to(PACKAGE_ROOT)
        target = package / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    return package


def _run_benchmark(package_parent: Path, output_root: Path) -> dict[str, object]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(package_parent)
    environment.pop("MEMORII_SOURCE_REVISION", None)
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "memorii.tools.run_eval",
            "--suite",
            "memory_evolution_sim_v1",
            "--mode",
            "llm",
            "--dry-run",
            "--storage-root",
            str(output_root),
            "--sim-profile",
            "long_horizon",
            "--sim-scenario-count",
            "1",
            "--sim-min-events",
            "5",
            "--sim-max-events",
            "10",
            "--sim-noise-rate",
            "0.35",
            "--seed",
            "7",
        ],
        cwd=output_root.parent,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    report_paths = list(output_root.rglob("report.json"))
    assert completed.stdout.startswith("suite=memory_evolution_sim_v1")
    assert len(report_paths) == 1
    report = json.loads(report_paths[0].read_text(encoding="utf-8"))
    assert isinstance(report, dict)
    return report


def _fingerprints(report: dict[str, object]) -> tuple[object, ...]:
    return tuple(report[field] for field in FINGERPRINT_FIELDS)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda package: (package / "fingerprint_probe.data").write_bytes(b"changed"),
        lambda package: (package / "added_probe.bin").write_bytes(b"added"),
        lambda package: (package / "fingerprint_probe.data").unlink(),
        lambda package: (package / "fingerprint_probe.data").rename(package / "renamed_probe.data"),
    ],
    ids=["change", "add", "remove", "rename"],
)
def test_public_benchmark_fingerprints_observe_owned_tree_mutations(
    tmp_path: Path,
    mutation: Callable[[Path], object],
) -> None:
    package_parent = tmp_path / "package"
    package = _copy_package(package_parent)
    probe = package / "fingerprint_probe.data"
    probe.write_bytes(b"before")
    before = _run_benchmark(package_parent, tmp_path / "before")

    mutation(package)
    after = _run_benchmark(package_parent, tmp_path / "after")

    assert all(left != right for left, right in zip(_fingerprints(before), _fingerprints(after), strict=True))


def test_public_benchmark_fingerprints_ignore_creation_order(tmp_path: Path) -> None:
    first_parent = tmp_path / "first-package"
    second_parent = tmp_path / "second-package"
    _copy_package(first_parent)
    _copy_package(second_parent, reverse=True)

    first = _run_benchmark(first_parent, tmp_path / "first-output")
    second = _run_benchmark(second_parent, tmp_path / "second-output")

    assert _fingerprints(first) == _fingerprints(second)


def test_public_benchmark_fingerprints_ignore_files_outside_package(tmp_path: Path) -> None:
    package_parent = tmp_path / "package"
    _copy_package(package_parent)
    outside = package_parent / "outside.txt"
    outside.write_text("before", encoding="utf-8")
    before = _run_benchmark(package_parent, tmp_path / "before")

    outside.write_text("after", encoding="utf-8")
    after = _run_benchmark(package_parent, tmp_path / "after")

    assert _fingerprints(before) == _fingerprints(after)


def test_public_benchmark_fingerprints_cover_dynamic_import_targets(tmp_path: Path) -> None:
    package_parent = tmp_path / "package"
    package = _copy_package(package_parent)
    (package / "dynamic_loader.py").write_text(
        "import importlib\nload = getattr(importlib, 'import_module')\nMODULE = load('memorii.dynamic_target')\n",
        encoding="utf-8",
    )
    target = package / "dynamic_target.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    before = _run_benchmark(package_parent, tmp_path / "before")

    target.write_text("VALUE = 2\n", encoding="utf-8")
    after = _run_benchmark(package_parent, tmp_path / "after")

    assert all(left != right for left, right in zip(_fingerprints(before), _fingerprints(after), strict=True))


def test_public_benchmark_fails_closed_on_package_symlink(tmp_path: Path) -> None:
    package_parent = tmp_path / "package"
    package = _copy_package(package_parent)
    outside = tmp_path / "outside.py"
    outside.write_text("VALUE = 1\n", encoding="utf-8")
    (package / "linked.py").symlink_to(outside)

    with pytest.raises(subprocess.CalledProcessError) as error:
        _run_benchmark(package_parent, tmp_path / "output")
    assert "installable package cannot contain symlinks: linked.py" in error.value.stderr


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions are required")
def test_public_benchmark_fails_closed_on_unreadable_package_file(tmp_path: Path) -> None:
    package_parent = tmp_path / "package"
    package = _copy_package(package_parent)
    unreadable = package / "unreadable.data"
    unreadable.write_bytes(b"owned")
    unreadable.chmod(0)
    try:
        with pytest.raises(subprocess.CalledProcessError) as error:
            _run_benchmark(package_parent, tmp_path / "output")
        assert "unreadable.data" in error.value.stderr
    finally:
        unreadable.chmod(0o600)
