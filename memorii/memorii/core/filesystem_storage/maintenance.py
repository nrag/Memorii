"""Soft-limit filesystem storage status helpers.

This module currently performs read-only status collection against configured
policy limits. It does not mutate files or execute compaction/archive flows.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from memorii.core.filesystem_storage.policy import FilesystemStoragePolicy


class StorageFileStatus(BaseModel):
    path: str
    exists: bool
    size_bytes: int
    exceeds_file_limit: bool

    model_config = ConfigDict(extra="forbid")


class StorageRootStatus(BaseModel):
    root_path: str
    total_bytes: int
    exceeds_total_limit: bool
    files: list[StorageFileStatus]

    model_config = ConfigDict(extra="forbid")


def collect_storage_status(root: str | Path, policy: FilesystemStoragePolicy) -> StorageRootStatus:
    root_path = Path(root)
    file_statuses: list[StorageFileStatus] = []
    total_bytes = 0

    if root_path.exists():
        for path in sorted(root_path.rglob("*")):
            if path.is_dir():
                continue
            size_bytes = path.stat().st_size
            total_bytes += size_bytes
            file_statuses.append(
                StorageFileStatus(
                    path=str(path),
                    exists=True,
                    size_bytes=size_bytes,
                    exceeds_file_limit=size_bytes > policy.max_file_bytes,
                )
            )

    return StorageRootStatus(
        root_path=str(root_path),
        total_bytes=total_bytes,
        exceeds_total_limit=total_bytes > policy.max_total_bytes,
        files=file_statuses,
    )


def ensure_within_soft_limits(root: str | Path, policy: FilesystemStoragePolicy) -> StorageRootStatus:
    """Return current status versus soft limits without mutating storage."""

    return collect_storage_status(root=root, policy=policy)
