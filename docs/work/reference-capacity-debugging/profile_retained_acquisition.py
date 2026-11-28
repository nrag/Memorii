"""Compare exact signed qualification acquisition across SQLite file layouts."""

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from checkpoint_capacity import emit, sample, timed
from native_cold_acquisition import copy_uncached, resident_pages

from memorii.stores.sqlite import raw_memory_payloads
from tests.support.reference_capacity_fixture import _installed_wheel_digest
from tests.support.reference_capacity_measure import _fresh_copy


def profile(root: Path, database: Path, expected_tuple: str) -> None:
    emit(type="residency_before", resident_pages=resident_pages(root / database)[0])
    parts: dict[str, int] = {}
    parity = raw_memory_payloads._require_index_parity

    def index_parity(connection: sqlite3.Connection, query: str, index: str, **options: str) -> None:
        timed(parts, f"parity:{index}", parity)(connection, query, index, **options)

    with (
        patch.object(raw_memory_payloads, "_advise_raw_read_ahead", timed(
            parts, "advice_ns", raw_memory_payloads._advise_raw_read_ahead,
        )),
        patch.object(raw_memory_payloads, "_require_index_parity", index_parity),
        patch.object(raw_memory_payloads, "_require_reference_closure", timed(
            parts, "references_ns", raw_memory_payloads._require_reference_closure,
        )),
    ):
        sample(root, expected_tuple, checkpoint=True)
    emit(type="raw_breakdown", **parts)


def compare(base: Path, report: Path, wheel: Path, work: Path) -> None:
    audit = json.loads(report.read_text())
    expected = audit["fixture"]["partition_tuple_digest"]
    if audit["wheel_sha256"] != _installed_wheel_digest(wheel):
        raise RuntimeError("installed wheel differs from qualification")
    database, = (path.relative_to(base) for path in base.glob("partition/generations/*/partition.sqlite3"))
    emit(type="identity", revision=audit["revision"], wheel_sha256=audit["wheel_sha256"], tuple_digest=expected)
    with _fresh_copy(base, work) as compact:
        with closing(sqlite3.connect(compact / database)) as connection:
            connection.execute("VACUUM")
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        for source in (base, compact, base, compact):
            with TemporaryDirectory(dir=work) as tmp:
                copy = Path(tmp) / "installation"
                shutil.copytree(source, copy, copy_function=copy_uncached)
                emit(
                    type="layout", layout="original" if source == base else "compacted",
                    database_bytes=(copy / database).stat().st_size,
                )
                subprocess.run([
                    sys.executable, __file__, "--base", str(copy),
                    "--database", str(database), "--tuple", expected,
                ], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--tuple")
    args = parser.parse_args()
    if args.database and args.tuple:
        profile(args.base, args.database, args.tuple)
    elif args.report and args.wheel and args.work:
        compare(args.base, args.report, args.wheel, args.work)
    else:
        parser.error("supply the qualification report, installed wheel, and work directory")


if __name__ == "__main__":
    main()
