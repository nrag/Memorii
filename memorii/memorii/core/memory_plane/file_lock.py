"""Cross-platform advisory file locking for persistent memory-plane stores."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import import_module
from pathlib import Path
from typing import BinaryIO, Protocol, cast

_WINDOWS = os.name == "nt"


class _WindowsLockApi(Protocol):
    LK_LOCK: int
    LK_RLCK: int
    LK_UNLCK: int

    def locking(self, file_descriptor: int, mode: int, byte_count: int) -> None: ...


@contextmanager
def locked_file(path: Path, *, exclusive: bool) -> Iterator[None]:
    """Hold a process-level advisory lock for the duration of the context."""
    with path.open("a+b") as handle:
        _acquire(handle, exclusive=exclusive)
        try:
            yield
        finally:
            _release(handle)


def _acquire(handle: BinaryIO, *, exclusive: bool) -> None:
    if _WINDOWS:
        windows_lock = _windows_lock_api()
        _ensure_lock_byte(handle)
        mode = windows_lock.LK_LOCK if exclusive else windows_lock.LK_RLCK
        windows_lock.locking(handle.fileno(), mode, 1)
        return

    import fcntl

    mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    fcntl.flock(handle.fileno(), mode)


def _release(handle: BinaryIO) -> None:
    if _WINDOWS:
        windows_lock = _windows_lock_api()
        handle.seek(0)
        windows_lock.locking(handle.fileno(), windows_lock.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _ensure_lock_byte(handle: BinaryIO) -> None:
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"\0")
        handle.flush()
        os.fsync(handle.fileno())
    handle.seek(0)


def _windows_lock_api() -> _WindowsLockApi:
    return cast(_WindowsLockApi, import_module("msvcrt"))
