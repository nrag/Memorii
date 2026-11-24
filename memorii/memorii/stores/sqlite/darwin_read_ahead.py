"""Advise reads from a process that owns no SQLite database locks."""

from __future__ import annotations

import fcntl
import os
import stat
import struct
import sys

_READ_AHEAD_LIMIT = 6 * 1024**3
_READ_AHEAD_SPAN = 32 * 1024**2
# Darwin sys/fcntl.h defines F_RDADVISE and struct radvisory (off_t, int).
_READ_ADVICE = 44
_READ_RANGE = struct.Struct("@qi4x")


def _advise(database: str) -> None:
    descriptor = os.open(database, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            return
        limit = min(info.st_size, _READ_AHEAD_LIMIT)
        for offset in range(0, limit, _READ_AHEAD_SPAN):
            length = min(_READ_AHEAD_SPAN, limit - offset)
            fcntl.fcntl(descriptor, _READ_ADVICE, _READ_RANGE.pack(offset, length))
    finally:
        os.close(descriptor)


if __name__ == "__main__" and sys.platform == "darwin":
    _advise(sys.argv[1])
