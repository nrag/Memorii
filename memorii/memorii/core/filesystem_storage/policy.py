"""Shared policy model for filesystem-backed Memorii JSONL stores.

This policy currently provides soft-limit configuration and maintenance hooks.
In this phase, the hooks only collect/report usage and limit exceedance status.
Compaction, archival, retention pruning, and other mutating maintenance actions
are intentionally deferred to later implementation phases.
"""

from pydantic import BaseModel, ConfigDict


class FilesystemStoragePolicy(BaseModel):
    """Soft-limit and future-maintenance configuration for filesystem storage."""

    max_total_bytes: int = 1_000_000_000
    max_file_bytes: int = 50_000_000
    max_retention_days: int = 30
    archive_enabled: bool = True
    compact_enabled: bool = True
    maintenance_interval_writes: int = 1000

    model_config = ConfigDict(extra="forbid")
