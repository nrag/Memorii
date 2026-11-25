"""Measure sealed startup and ordinary verification on exact disposable fixtures."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic_ns
from unittest.mock import patch

from checkpoint_capacity import change_mode, emit, sample, timed
from memorii.core.storage_administration.service import StorageAdministrationService
from native_cold_acquisition import copy_uncached, resident_pages
from sealed_startup import (
    ImageSeal,
    SealedStartupError,
    acquire,
    frozen_fixture,
    issue_seal,
)
from tests.support.reference_capacity_fixture import _installed_wheel_digest


def prepare_fixture(root: Path, original: str) -> tuple[Path, str]:
    with StorageAdministrationService(root) as owner:
        path, before = owner._active_partition_selection()
        if before is None or before.payload_digest() != original:
            raise RuntimeError("retained fixture signed head differs")
        if owner._require_operational().mode != "read_only":
            change_mode(owner, "read_only")
        _, after = owner._active_partition_selection()
        if (
            after is None or before.vector.runtime_position != after.vector.runtime_position
            or before.manifest_digest != after.manifest_digest or before.checkpoint_digest != after.checkpoint_digest
            or before.data_generation_id != after.data_generation_id
        ):
            raise RuntimeError("owner staging changed the logical qualification fixture")
    with closing(sqlite3.connect(path)) as connection:
        status = tuple(connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone())
        if status[0] != 0:
            raise RuntimeError("fixture WAL could not be fully checkpointed")
    return path, after.payload_digest()


def persist_fixture_seal(root: Path, seal: ImageSeal) -> None:
    # Only this process can reach the private benchmark tree during setup.
    path = root / "control" / "verified_image.json"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(seal.model_dump_json())


def measure(root: Path, expected: str, verifier: str, mode: str, distribution: str, pair: int) -> None:
    path, = root.glob("partition/generations/*/partition.sqlite3")
    if resident_pages(path)[0]:
        raise RuntimeError("cold copy has resident data pages")
    if mode == "sealed":
        def forbid_scan(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("sealed startup called the full logical verifier")

        with (
            frozen_fixture(root, path),
            patch.object(StorageAdministrationService, "_matches_materialization", forbid_scan),
            patch("sealed_startup._exact_verification", forbid_scan),
        ):
            start = monotonic_ns()
            with StorageAdministrationService(root) as owner:
                opened = monotonic_ns()
                result, length = acquire(owner, verifier)
                done = monotonic_ns()
        if result != expected:
            raise RuntimeError("sealed acquisition selected a different publication")
        metrics = {
            "tuple_digest": result, "image_bytes": length, "service_open_ns": opened - start,
            "elapsed_ns": done - opened, "startup_ns": done - start, "logical_scan_calls": 0,
        }
    else:
        components: dict[str, int] = {}
        output = io.StringIO()
        with (
            patch.object(
                StorageAdministrationService, "__init__",
                timed(components, "service_open_ns", StorageAdministrationService.__init__),
            ),
            redirect_stdout(output),
        ):
            sample(root, expected, checkpoint=True)
        metrics = json.loads(output.getvalue())
        metrics.pop("type")
        metrics["startup_ns"] = metrics["elapsed_ns"] + components["service_open_ns"]
        metrics.update(components)
    emit(type="acquisition", distribution=distribution, pair=pair, mode=mode, resident_pages=0, **metrics)


def verify_tamper_denial(root: Path, path: Path, expected: str, verifier: str, distribution: str) -> None:
    with closing(sqlite3.connect(path)) as external:
        rowid, = external.execute("SELECT min(rowid) FROM memory_payloads").fetchone()
        with external, external.blobopen("memory_payloads", "body", rowid) as blob:
            blob[-1] ^= 1
        actual, = external.execute("SELECT tuple_digest FROM partition_publication").fetchone()
        if actual != expected:
            raise RuntimeError("mutation changed the fixture publication row")
    with frozen_fixture(root, path), StorageAdministrationService(root) as owner:
        try:
            acquire(owner, verifier)
        except SealedStartupError as exc:
            if str(exc) != "sealed byte image differs":
                raise
            emit(type="tamper", distribution=distribution, staged_tuple=expected, outcome="denied", mutation="raw_body")
        else:
            raise RuntimeError("the tampered image reached readiness")


def compare(fixtures: Path, reports: Path, work: Path, wheel: Path, pairs: int) -> None:
    package = _installed_wheel_digest(wheel)
    verifier = hashlib.sha256(f"{package}:{sqlite3.sqlite_version}:sealed-fixture-v1".encode()).hexdigest()
    for distribution in ("balanced", "concentrated"):
        report = json.loads((reports / f"{distribution}-measurement.json").read_text())
        original = report["fixture"]["partition_tuple_digest"]
        with TemporaryDirectory(dir=work) as staging:
            staged = Path(staging) / "installation"
            shutil.copytree(fixtures / distribution, staged)
            path, expected = prepare_fixture(staged, original)
            start = monotonic_ns()
            with frozen_fixture(staged, path):
                seal = issue_seal(staged, verifier)
            persist_fixture_seal(staged, seal)
            emit(
                type="identity", distribution=distribution, source_revision=report["revision"], original_tuple=original,
                staged_tuple=expected, wheel=package, sqlite_version=sqlite3.sqlite_version, verifier=verifier,
                image=seal.image, image_bytes=seal.length, seal_elapsed_ns=monotonic_ns() - start,
            )
            for pair in range(pairs):
                order = ("ordinary", "sealed")
                if (pair + (distribution == "concentrated")) % 2:
                    order = tuple(reversed(order))
                for mode in order:
                    with TemporaryDirectory(dir=work) as scratch:
                        root = Path(scratch) / "installation"
                        shutil.copytree(staged, root, copy_function=copy_uncached)
                        subprocess.run(
                            [sys.executable, __file__, "sample", str(root), expected, verifier, mode, distribution, str(pair)],
                            check=True,
                        )
            verify_tamper_denial(staged, path, expected, verifier, distribution)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("compare")
    run.add_argument("--fixtures", type=Path, required=True)
    run.add_argument("--reports", type=Path, required=True)
    run.add_argument("--work", type=Path, required=True)
    run.add_argument("--wheel", type=Path, required=True)
    run.add_argument("--pairs", type=int, default=2)
    child = commands.add_parser("sample")
    child.add_argument("root", type=Path)
    child.add_argument("expected")
    child.add_argument("verifier")
    child.add_argument("mode", choices=("ordinary", "sealed"))
    child.add_argument("distribution")
    child.add_argument("pair", type=int)
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("fixture custody requires native macOS")
    if args.command == "compare":
        if args.pairs < 1:
            parser.error("positive number of pairs required")
        compare(args.fixtures, args.reports, args.work, args.wheel, args.pairs)
    else:
        measure(args.root, args.expected, args.verifier, args.mode, args.distribution, args.pair)


if __name__ == "__main__":
    main()
