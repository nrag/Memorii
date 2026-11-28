"""Compare exact acquisition from installed wheels on retained native fixtures."""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from checkpoint_capacity import emit, sample, timed
from memorii.core.storage_administration.service import StorageAdministrationService
from native_cold_acquisition import copy_uncached, resident_pages
from tests.support.reference_capacity_fixture import _installed_wheel_digest


def measure(root: Path, expected: str, wheel: Path, mode: str, distribution: str, pair: int) -> None:
    digest = _installed_wheel_digest(wheel)
    database, = root.glob("partition/generations/*/partition.sqlite3")
    resident, total_pages = resident_pages(database)
    if resident != 0:
        raise RuntimeError(f"selected main file had {resident} resident pages before acquisition")
    initialization: dict[str, int] = {}
    output = io.StringIO()
    with (
        patch.object(
            StorageAdministrationService, "__init__",
            timed(initialization, "service_open_ns", StorageAdministrationService.__init__),
        ),
        redirect_stdout(output),
    ):
        sample(root, expected, checkpoint=True)
    metrics = json.loads(output.getvalue())
    emit(
        **metrics, distribution=distribution, mode=mode, pair=pair, wheel_digest=digest,
        sqlite_version=sqlite3.sqlite_version, resident_pages=resident, database_pages=total_pages,
        startup_ns=initialization["service_open_ns"] + metrics["elapsed_ns"], **initialization,
    )


def compare(
    fixtures: Path, reports: Path, work: Path,
    baseline: tuple[str, str], candidate: tuple[str, str], pairs: int,
) -> None:
    arms = {"baseline": baseline, "candidate": candidate}
    for distribution in ("balanced", "concentrated"):
        report = json.loads((reports / f"{distribution}-measurement.json").read_text())
        expected = report["fixture"]["partition_tuple_digest"]
        emit(
            type="identity", distribution=distribution, revision=report["revision"],
            qualification_wheel=report["wheel_sha256"], tuple_digest=expected,
        )
        for pair in range(pairs):
            order = ("baseline", "candidate")
            if (pair + (distribution == "concentrated")) % 2:
                order = tuple(reversed(order))
            for mode in order:
                site, wheel = arms[mode]
                env = {**os.environ, "PYTHONPATH": site + os.pathsep + os.environ["PYTHONPATH"]}
                with TemporaryDirectory(prefix="raw-verification-", dir=work) as scratch:
                    root = Path(scratch) / "installation"
                    shutil.copytree(fixtures / distribution, root, copy_function=copy_uncached)
                    subprocess.run(
                        [sys.executable, __file__, "sample", str(root), expected, wheel, mode, distribution, str(pair)],
                        env=env, check=True,
                    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("compare")
    run.add_argument("--fixtures", type=Path, required=True)
    run.add_argument("--reports", type=Path, required=True)
    run.add_argument("--work", type=Path, required=True)
    run.add_argument("--baseline", nargs=2, required=True, metavar=("SITE", "WHEEL"))
    run.add_argument("--candidate", nargs=2, required=True, metavar=("SITE", "WHEEL"))
    run.add_argument("--pairs", type=int, default=2)
    child = commands.add_parser("sample")
    child.add_argument("root", type=Path)
    child.add_argument("expected")
    child.add_argument("wheel", type=Path)
    child.add_argument("mode")
    child.add_argument("distribution")
    child.add_argument("pair", type=int)
    args = parser.parse_args()
    if args.command == "sample":
        measure(args.root, args.expected, args.wheel, args.mode, args.distribution, args.pair)
    else:
        if sys.platform != "darwin" or args.pairs < 1:
            parser.error("comparison requires native macOS and a positive number of pairs")
        compare(args.fixtures, args.reports, args.work, args.baseline, args.candidate, args.pairs)


if __name__ == "__main__":
    main()
