"""Private owner harness for the retained SQLite VFS feasibility test."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import ExitStack, closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from secrets import token_hex
from typing import TypeVar

_BLOCK_BYTES = 65_536
_MAX_IMAGE_BYTES = 8 * 1024**3
_ROOT = b"memorii.sealed-image-root.v2\0"
_BLOCK = b"memorii.sealed-image-block.v2\0"
_T = TypeVar("_T")


class ReleaseDenied(RuntimeError):
    """The retained image could not authorize a protected result."""


@dataclass(frozen=True)
class ReadStats:
    failed: bool
    calls: int
    blocks: int


def block_table(descriptor: int) -> tuple[int, bytes, str]:
    length = os.fstat(descriptor).st_size
    if not 0 < length <= _MAX_IMAGE_BYTES:
        raise ReleaseDenied("image size is outside the sealed profile")
    table = bytearray()
    for offset in range(0, length, _BLOCK_BYTES):
        expected = min(_BLOCK_BYTES, length - offset)
        body = os.pread(descriptor, expected, offset)
        if len(body) != expected:
            raise ReleaseDenied("short read while authenticating the image")
        index = offset // _BLOCK_BYTES
        table.extend(hashlib.sha256(_BLOCK + index.to_bytes(8, "big") + body).digest())
    if os.pread(descriptor, 1, length):
        raise ReleaseDenied("image grew while authenticating")
    root = hashlib.sha256(_ROOT + length.to_bytes(8, "big") + table).hexdigest()
    return length, bytes(table), root


def _authorize(action: int, _target: str | None, _option: str | None, _db: str | None, _view: str | None) -> int:
    if action in (sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH, sqlite3.SQLITE_PRAGMA):
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


class RetainedReader:
    def __init__(self, control: sqlite3.Connection, database: sqlite3.Connection) -> None:
        self._control = control
        self._database = database

    def stats(self) -> ReadStats:
        failed, calls, blocks = json.loads(self._control.execute("SELECT fixture_status()").fetchone()[0])
        return ReadStats(bool(failed), calls, blocks)

    def _require_intact(self) -> None:
        if self.stats().failed:
            raise ReleaseDenied("retained image integrity is latched closed")

    def release(
        self, operation: Callable[[sqlite3.Connection], _T], *, before_release: Callable[[], None] | None = None,
    ) -> _T:
        """Gate a fully materialized result from a trusted callback on the native latch."""
        self._require_intact()
        try:
            result = operation(self._database)
        except sqlite3.DatabaseError:
            self._require_intact()
            raise
        if before_release is not None:
            before_release()
        self._require_intact()
        return result


@contextmanager
def retained_reader(path: Path, expected_root: str, extension: Path) -> Iterator[RetainedReader]:
    # The isolated runner supplies the expected root from prior full byte
    # verification. No image path or native handle is made available to clients.
    if any(os.path.lexists(str(path) + suffix) for suffix in ("-journal", "-wal", "-shm")):
        raise ReleaseDenied("expected one self-contained SQLite image")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    with ExitStack() as stack:
        stack.callback(os.close, descriptor)
        length, table, root = block_table(descriptor)
        if not hmac.compare_digest(root, expected_root):
            raise ReleaseDenied("image root differs from the precomputed root")
        control = stack.enter_context(closing(sqlite3.connect(":memory:")))
        control.enable_load_extension(True)
        try:
            control.load_extension(str(extension), entrypoint="sqlite3_retainedvfs_init")
        finally:
            control.enable_load_extension(False)
        # Validate both controls first and register cleanup before a pin can be allocated.
        control.execute("SELECT fixture_drop_pending(), fixture_status() LIMIT 0").close()
        stack.callback(lambda: control.execute("SELECT fixture_drop_pending()").close())
        token, = control.execute("SELECT fixture_pin(?, ?, ?, ?)", (descriptor, length, table, token_hex(16))).fetchone()
        database = stack.enter_context(closing(sqlite3.connect(
            f"file:{token}?vfs=memorii-retained-test&mode=ro&cache=private", uri=True,
        )))
        database.execute("PRAGMA query_only=ON")
        database.execute("PRAGMA temp_store=MEMORY")
        database.execute("PRAGMA cache_size=-64")
        database.execute("PRAGMA trusted_schema=OFF")
        database.set_authorizer(_authorize)
        yield RetainedReader(control, database)
