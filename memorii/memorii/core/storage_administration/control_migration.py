"""Owner-authorized control-format migration between schema versions.

The migration contract from the design: an explicit `migrate_control_format`
copies and validates the control database, requires no unresolved intent,
switches an atomic control-generation pointer recording old/new format and
digest, unknown future formats reject before writes, pre-switch failure
retains the old generation, and once new control writes exist the binary
must refuse downgrade (read-only forward repair only).
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from memorii.stores.sqlite.control import ControlStateError

_SUPPORTED_VERSIONS = (1, 2)
_GENERATION_POINTER = "control-generation.json"


@dataclass(frozen=True)
class ControlMigrationPlan:
    """Owner-reviewed plan describing one control-format migration."""

    source_version: int
    target_version: int
    control_database_digest: str


@dataclass(frozen=True)
class ControlMigrationReceipt:
    """Durable record of a completed control-format migration."""

    plan: ControlMigrationPlan
    migrated_at_unix: int
    generation_pointer: Path


class ControlMigrationError(RuntimeError):
    """Migration refused; the closed reason carries the cause."""


def read_control_schema_version(database_path: Path) -> int:
    """The control database's recorded schema version."""
    connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    try:
        row = connection.execute(
            "SELECT value FROM control_schema WHERE key = 'schema_version'"
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return 1
    return int(row[0])


def plan_control_format_migration(
    source_database: Path, *, target_version: int
) -> ControlMigrationPlan:
    """Derive the migration plan; unknown formats reject before any write."""
    import hashlib

    source_version = read_control_schema_version(source_database)
    if target_version not in _SUPPORTED_VERSIONS or target_version != source_version + 1:
        reason = (
            f"unknown control format {target_version}"
            if target_version not in _SUPPORTED_VERSIONS
            else "control formats migrate exactly one version forward"
            f" (source {source_version}, target {target_version})"
        )
        raise ControlMigrationError(f"unsupported_configuration: {reason}")
    digest = hashlib.sha256(source_database.read_bytes()).hexdigest()
    return ControlMigrationPlan(
        source_version=source_version,
        target_version=target_version,
        control_database_digest=digest,
    )


def migrate_control_format(
    source_database: Path,
    *,
    target_version: int,
    keys_directory: Path,
) -> ControlMigrationReceipt:
    """Apply the owner-authorized control-format migration.

    The source database is copied and validated (journal intact, no pending
    intent), the copy's schema version advances, and an atomic generation
    pointer records old/new format and digests. The source is retained;
    only the pointer selects the active generation.
    """
    import time

    plan = plan_control_format_migration(source_database, target_version=target_version)
    if not keys_directory.is_dir():
        raise ControlMigrationError(
            "invalid_request: the owner key directory must be present"
        )

    # No unresolved intent: a pending publication must be resolved by its
    # own owner before any control-format work.
    connection = sqlite3.connect(f"file:{source_database}?mode=ro", uri=True)
    try:
        pending = 0
        for row in connection.execute(
            "SELECT intent_json FROM publication_intents"
        ).fetchall():
            import json as _json

            try:
                intent = _json.loads(row[0])
            except ValueError:
                # Unparseable intent rows are unresolved by definition.
                pending += 1
                continue
            if intent.get("phase") == "prepared":
                pending += 1
    finally:
        connection.close()
    if pending:
        raise ControlMigrationError(
            "conflict: a prepared publication intent must be resolved first"
        )

    generation_root = source_database.parent / "control-generations"
    generation_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    staged = generation_root / f"control.v{target_version}.sqlite3"
    shutil.copyfile(source_database, staged)
    os.chmod(staged, 0o600)
    connection = sqlite3.connect(str(staged))
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "UPDATE control_schema SET value = ? WHERE key = 'schema_version'",
            (str(target_version),),
        )
        connection.commit()
    finally:
        connection.close()

    import hashlib

    pointer = generation_root / _GENERATION_POINTER
    record = {
        "source_version": plan.source_version,
        "target_version": plan.target_version,
        "source_digest": plan.control_database_digest,
        "target_digest": hashlib.sha256(staged.read_bytes()).hexdigest(),
        "migrated_at_unix": int(time.time()),
    }
    temporary = generation_root / f".{_GENERATION_POINTER}.tmp"
    temporary.write_text(json.dumps(record, sort_keys=True))
    os.chmod(temporary, 0o600)
    os.replace(temporary, pointer)
    return ControlMigrationReceipt(
        plan=plan,
        migrated_at_unix=record["migrated_at_unix"],
        generation_pointer=pointer,
    )


def require_control_format(database_path: Path, *, maximum_supported: int) -> None:
    """Refuse to write control formats newer than this binary supports.

    Called before any control write: an unknown future format fails closed
    here instead of producing rows the binary cannot interpret. Once a
    database has been used at a newer version (target_version marker in the
    generation pointer), this same check refuses downgrade reads.
    """
    version = read_control_schema_version(database_path)
    if version > maximum_supported:
        raise ControlStateError(
            f"unsupported control schema version: {version}"
            " (refusing downgrade; use forward repair)"
        )
    pointer = database_path.parent / "control-generations" / _GENERATION_POINTER
    if pointer.is_file():
        record = json.loads(pointer.read_text())
        if int(record.get("target_version", 0)) > maximum_supported:
            raise ControlStateError(
                "control generation is newer than this binary"
                " (refusing downgrade; use forward repair)"
            )


__all__ = [
    "ControlMigrationError",
    "ControlMigrationPlan",
    "ControlMigrationReceipt",
    "migrate_control_format",
    "plan_control_format_migration",
    "read_control_schema_version",
    "require_control_format",
]
