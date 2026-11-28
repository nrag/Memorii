"""Private input files for operator CLI tests."""

from __future__ import annotations

import os
from pathlib import Path


def write_owner_file(path: Path, value: str | bytes) -> str:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(value.encode("ascii") if isinstance(value, str) else value)
    return str(path)
