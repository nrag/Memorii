"""Private concurrent transport and drain harness; clients never receive SQLite handles."""

from __future__ import annotations

import ctypes
import errno
import os
import select
import socket
import sqlite3
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from threading import Event, Lock
from time import monotonic

from memorii.core.harness_state.grant_registry import GrantEpochRegistry
from memorii.core.memory_plane.file_lock import locked_file
from retained_vfs_probe import ReleaseDenied, RetainedReader, retained_reader

_MAX_RESPONSE = 512 * 1024
_SOCKET_CHUNK = 16 * 1024


class DrainBusy(RuntimeError):
    """The sealed owner still holds live work."""


class RetainedWorker:
    """A single SQLite owner thread and trusted concurrent response tasks."""

    def __init__(self, root: Path, image: Path, expected_root: str, extension: Path) -> None:
        self.root = root
        self._publication = root / ".publication.lock"
        self._lifetime = root / "control" / ".backup-lifetime.lock"
        self._grants = GrantEpochRegistry(root / "control" / "grants")
        self._admitting = True
        self._active = 0
        self._idle = Event()
        self._idle.set()
        self._drain_lock = Lock()
        self._closed = False
        self._executor = ThreadPoolExecutor(max_workers=1)
        native = ctypes.CDLL(str(extension), use_errno=True)
        self._send = native.fixture_send_retained
        self._send.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_size_t)
        self._send.restype = ctypes.c_ssize_t
        self._stack = ExitStack()

        def open_owner() -> RetainedReader:
            with ExitStack() as pending:
                pending.enter_context(locked_file(self._lifetime, exclusive=False))
                reader = pending.enter_context(retained_reader(image, expected_root, extension))
                self._stack = pending.pop_all()
                return reader

        try:
            self._reader = self._executor.submit(open_owner).result()
        except BaseException:
            self._executor.shutdown()
            raise

    def _authorize(self, grant: str, epoch: int) -> None:
        if not self._admitting:
            raise ReleaseDenied("sealed worker admissions are closed")
        self._grants.require_current(grant, epoch)

    def revoke(self, grant: str) -> None:
        with locked_file(self._publication, exclusive=True):
            self._grants.revoke(grant, reason="test owner revocation")

    def serve(
        self, connection: socket.socket, grant: str, epoch: int,
        read: Callable[[sqlite3.Connection], bytes], *, before_send: Callable[[], None] | None = None,
        on_backpressure: Callable[[], None] | None = None,
    ) -> int:
        with connection:
            connection.setblocking(False)
            with locked_file(self._publication, exclusive=True):
                self._authorize(grant, epoch)
                self._active += 1
                self._idle.clear()
            try:
                result = self._executor.submit(self._reader.release, read).result()
                if len(result) > _MAX_RESPONSE:
                    raise ReleaseDenied("response exceeds fixture buffer limit")
                if before_send is not None:
                    before_send()
                offset = 0
                deadline = monotonic() + 5
                while offset < len(result):
                    chunk = result[offset:offset + _SOCKET_CHUNK]
                    with locked_file(self._publication, exclusive=True):
                        self._authorize(grant, epoch)
                        sent = self._send(connection.fileno(), chunk, len(chunk))
                        error = ctypes.get_errno() if sent < 0 else 0
                    if sent > 0:
                        offset += sent
                    elif error in (errno.EAGAIN, errno.EWOULDBLOCK):
                        if on_backpressure is not None:
                            on_backpressure()
                        if not select.select([], [connection], [], max(0, deadline - monotonic()))[1]:
                            raise ReleaseDenied("socket write timed out")
                    elif error == errno.EACCES:
                        raise ReleaseDenied("retained image integrity is latched closed")
                    else:
                        raise OSError(error or errno.EIO, os.strerror(error or errno.EIO))
                return offset
            finally:
                # Drop unsent bytes and close the stream before acknowledging drain.
                result = chunk = b""
                connection.close()
                with locked_file(self._publication, exclusive=True):
                    self._active -= 1
                    if self._active == 0:
                        self._idle.set()

    def drain(self, *, timeout: float) -> None:
        with self._drain_lock:
            if self._closed:
                return
            with locked_file(self._publication, exclusive=True):
                self._admitting = False
            if not self._idle.wait(timeout):
                raise DrainBusy("sealed responses still hold custody")
            self._executor.submit(self._stack.close).result()
            self._executor.shutdown()
            self._closed = True
