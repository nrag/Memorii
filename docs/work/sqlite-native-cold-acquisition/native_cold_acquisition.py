"""Time native macOS acquisition on fresh, residency-checked SSD copies."""

from __future__ import annotations

import argparse
import ctypes
import fcntl
import hashlib
import mmap
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from checkpoint_capacity import emit, sample
from tests.support.reference_capacity_fixture import _installed_wheel_digest


def copy_uncached(source: str, target: str) -> str:
    with open(source, "rb", buffering=0) as reader, open(target, "xb", buffering=0) as writer:
        fcntl.fcntl(reader.fileno(), fcntl.F_NOCACHE, 1)
        fcntl.fcntl(writer.fileno(), fcntl.F_NOCACHE, 1)
        shutil.copyfileobj(reader, writer, length=1024 * 1024)
        os.fsync(writer.fileno())
    shutil.copystat(source, target)
    return target


def resident_pages(path: Path) -> tuple[int, int]:
    """Read vnode residency without faulting file pages into memory."""
    libc = ctypes.CDLL(None, use_errno=True)
    libc.mmap.argtypes = (
        ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int64,
    )
    libc.mmap.restype = ctypes.c_void_p
    libc.mincore.argtypes = (ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_ubyte))
    libc.mincore.restype = ctypes.c_int
    libc.munmap.argtypes = (ctypes.c_void_p, ctypes.c_size_t)
    libc.munmap.restype = ctypes.c_int
    with path.open("rb") as database:
        size = os.fstat(database.fileno()).st_size
        pages = (size + mmap.PAGESIZE - 1) // mmap.PAGESIZE
        vector = (ctypes.c_ubyte * pages)()
        address = libc.mmap(None, size, mmap.PROT_READ, mmap.MAP_SHARED, database.fileno(), 0)
        if address == ctypes.c_void_p(-1).value:
            raise OSError(ctypes.get_errno(), "could not map fixture for residency measurement")
        try:
            if libc.mincore(address, size, vector) != 0:
                raise OSError(ctypes.get_errno(), "could not measure fixture page residency")
            return sum(bool(flags & 1) for flags in vector), pages
        finally:
            libc.munmap(address, size)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--expected-tuple", required=True)
    parser.add_argument("--database", required=True, type=Path, help="selected database path relative to base")
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--sample", action="store_true")
    parser.add_argument("--sample-index", type=int, default=0)
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("the SSD residency protocol requires native macOS")
    database = args.base / args.database
    if not database.resolve().is_relative_to(args.base.resolve()):
        parser.error("database must be inside the copied synthetic fixture")
    if args.sample:
        before, pages = resident_pages(database)
        emit(type="residency_before", sample_index=args.sample_index, resident_pages=before, total_pages=pages)
        sample(args.base, args.expected_tuple, checkpoint=True)
        after, pages = resident_pages(database)
        emit(type="residency_after", sample_index=args.sample_index, resident_pages=after, total_pages=pages)
        return
    if args.wheel is None or args.work is None or args.samples < 1:
        parser.error("provide the installed wheel, work directory, and positive sample count")
    runner = Path(__file__)
    emit(
        type="identity", wheel_digest=_installed_wheel_digest(args.wheel),
        runner_digest=hashlib.sha256(runner.read_bytes()).hexdigest(),
        acquisition_runner_digest=hashlib.sha256(runner.with_name("checkpoint_capacity.py").read_bytes()).hexdigest(),
        sqlite_version=sqlite3.sqlite_version, platform=platform.platform(), python=platform.python_version(),
        database_bytes=database.stat().st_size, page_bytes=mmap.PAGESIZE,
    )
    for index in range(args.samples):
        with TemporaryDirectory(prefix="native-cold-", dir=args.work) as scratch:
            root = Path(scratch) / "installation"
            shutil.copytree(args.base, root, copy_function=copy_uncached)
            subprocess.run(
                [
                    sys.executable, str(runner), "--base", str(root), "--expected-tuple", args.expected_tuple,
                    "--database", str(args.database), "--sample", "--sample-index", str(index),
                ],
                check=True,
            )


if __name__ == "__main__":
    main()
