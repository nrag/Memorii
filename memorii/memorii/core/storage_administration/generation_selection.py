"""Signed physical selection for one finalized managed data generation."""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.persistence.contracts import canonical_json_digest

PARTITION_GENERATION_SELECTOR = "partition-generation.json"
_MAX_SELECTOR_BYTES = 8192
_GENERATION_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$"


class PartitionGenerationSelector(BaseModel):
    """Select a generation by coordinate, with the physical path derived locally."""

    format_version: Literal[1] = 1
    installation_id: str = Field(min_length=1, max_length=512, pattern=r"^[^\x00]+$")
    repository_id: str = Field(min_length=1, max_length=512, pattern=r"^[^\x00]+$")
    generation_id: str = Field(pattern=_GENERATION_PATTERN)
    signature: str = Field(pattern=r"^[0-9a-f]{128}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    def unsigned_digest(self) -> str:
        return canonical_json_digest(self.model_dump(mode="json", exclude={"signature"}))


def read_partition_generation_selector(control_root: Path) -> PartitionGenerationSelector | None:
    """Read the typed, bounded pointer. Authentication belongs to the control owner."""
    path = control_root / PARTITION_GENERATION_SELECTOR
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    except FileNotFoundError:
        return None
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or path.is_symlink():
            raise ValueError("partition generation selector must be an owner-only regular file")
        payload = handle.read(_MAX_SELECTOR_BYTES + 1)
    if len(payload) > _MAX_SELECTOR_BYTES:
        raise ValueError("partition generation selector is too large")
    return PartitionGenerationSelector.model_validate_json(payload)


def selected_partition_path(partition_root: Path, generation_id: str) -> Path:
    """Resolve the named generation without admitting caller paths or symlinks."""
    if re.fullmatch(_GENERATION_PATTERN, generation_id) is None:
        raise ValueError("partition generation coordinate is invalid")
    generations = partition_root / "generations"
    directory = generations / generation_id
    path = directory / "partition.sqlite3"
    for location in (partition_root, generations, directory, path):
        if location.is_symlink():
            raise ValueError("selected partition generation contains a symlink")
    if not path.is_file():
        raise ValueError("selected partition generation is missing")
    return path
