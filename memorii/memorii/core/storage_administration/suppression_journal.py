"""Typed suppression journal: the durable revocation watermark.

The journal is the control-plane record of every logical forget. It is
written BEFORE the enforcement publication and survives restore; each
entry carries only content-free coordinates and digests. Readers accept
the legacy untyped v1 shape (task ids from the first release) and the
versioned v2 envelope, and reject unknown versions fail-closed.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_JOURNAL_VERSION = 2
_HEX_64 = r"^[0-9a-f]{64}$"


class SuppressionCoordinate(BaseModel):
    """One content-free revocation coordinate."""

    coordinate_kind: Literal[
        "entity", "claim", "source", "record", "task", "justification"
    ]
    coordinate_id: str = Field(min_length=1)
    record_kind: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class SuppressionRecord(BaseModel):
    """The versioned journal entry for one applied forget."""

    journal_version: Literal[2] = 2
    suppression_id: str = Field(pattern=_HEX_64)
    plan_digest: str = Field(pattern=_HEX_64)
    closure_digest: str = Field(pattern=_HEX_64)
    scope_note: str
    suppressed: tuple[SuppressionCoordinate, ...]
    applied_at_unix: int = Field(ge=0)
    control_journal_position: int = Field(default=1, ge=1)
    # The owner-capability digest presented at apply; None only for
    # legacy entries written before the field existed.
    authority_capability_digest: str | None = Field(default=None, pattern=_HEX_64)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("suppressed")
    @classmethod
    def _canonical_suppressed(
        cls, values: tuple[SuppressionCoordinate, ...]
    ) -> tuple[SuppressionCoordinate, ...]:
        keys = tuple(
            (item.coordinate_kind, item.coordinate_id, item.record_kind)
            for item in values
        )
        if not keys or keys != tuple(sorted(set(keys))):
            raise ValueError("suppression coordinates must be nonempty and canonical")
        return values


def suppression_identifier(
    *, installation_id: str, plan_digest: str, closure_digest: str
) -> str:
    """Derive the stable, content-free suppression identity.

    Derived from content coordinates only — never filenames or timestamps
    — so it is invariant under journal copy, restore, boot, and any future
    compaction or rename.
    """

    return sha256(
        b"memorii.suppression-identifier.v1\0"
        + installation_id.encode()
        + b"\0"
        + plan_digest.encode()
        + b"\0"
        + closure_digest.encode()
    ).hexdigest()


def journal_directory(control_root: Path) -> Path:
    return control_root / "suppressions"


def write_suppression_record(
    control_root: Path, record: SuppressionRecord
) -> Path:
    """Durably append one journal entry (0o600, atomic rename)."""

    directory = journal_directory(control_root)
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    payload = (json.dumps(record.model_dump(mode="json"), sort_keys=True) + "\n").encode()
    # The suppression_id is unique per plan and stable across retries, so
    # distinct suppressions applied within the same second can never
    # collide (a retry of the same plan rewrites its own entry, which is
    # the intended idempotence).
    path = directory / (
        f"forget-{record.applied_at_unix * 1000}-{record.suppression_id[:16]}.json"
    )
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
    return path


def read_suppression_records(control_root: Path) -> tuple[SuppressionRecord, ...]:
    """Parse every journal entry; v1 legacy entries normalize, unknown fail closed."""

    directory = journal_directory(control_root)
    if not directory.exists():
        return ()
    records: list[SuppressionRecord] = []
    for path in sorted(directory.glob("forget-*.json")):
        try:
            raw = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            raise ValueError(f"suppression journal entry is unreadable: {path.name}") from exc
        if not isinstance(raw, dict):
            raise ValueError(f"suppression journal entry is not an object: {path.name}")
        version = raw.get("journal_version")
        if version == _JOURNAL_VERSION:
            try:
                records.append(SuppressionRecord.model_validate(raw))
            except ValueError as exc:
                raise ValueError(
                    f"suppression journal entry is invalid: {path.name}"
                ) from exc
        elif version is None and "suppressed" in raw and "applied_at_unix" in raw:
            # Legacy v1: untyped task-id entries from the first release.
            suppressed = raw.get("suppressed")
            if not isinstance(suppressed, list) or not all(
                isinstance(item, str) and item for item in suppressed
            ):
                raise ValueError(
                    f"suppression journal legacy entry is invalid: {path.name}"
                )
            for item in sorted(suppressed):
                records.append(
                    SuppressionRecord(
                        suppression_id=sha256(
                            b"memorii.suppression-legacy-identifier.v1\0"
                            + path.name.encode()
                            + b"\0"
                            + item.encode()
                        ).hexdigest(),
                        plan_digest=sha256(
                            b"memorii.suppression-legacy-plan.v1\0" + path.name.encode()
                        ).hexdigest(),
                        closure_digest=sha256(
                            b"memorii.suppression-legacy-closure.v1\0" + path.name.encode()
                        ).hexdigest(),
                        scope_note=str(raw.get("scope_note", "")),
                        suppressed=(
                            SuppressionCoordinate(
                                coordinate_kind="task", coordinate_id=item
                            ),
                        ),
                        applied_at_unix=int(raw["applied_at_unix"]),
                    )
                )
        else:
            raise ValueError(
                f"suppression journal entry version is unsupported: {path.name}"
            )
    return tuple(records)


def suppressed_coordinates(control_root: Path) -> tuple[SuppressionCoordinate, ...]:
    """Union of every journal entry's coordinates (the restore watermark)."""

    by_key: dict[str, SuppressionCoordinate] = {}
    for record in read_suppression_records(control_root):
        for coordinate in record.suppressed:
            key = (
                f"{coordinate.coordinate_kind}|{coordinate.coordinate_id}"
                f"|{coordinate.record_kind or ''}"
            )
            by_key.setdefault(key, coordinate)
    return tuple(
        sorted(
            by_key.values(),
            key=lambda item: (
                item.coordinate_kind, item.coordinate_id, item.record_kind or ""
            ),
        )
    )


def find_record_by_plan_digest(
    control_root: Path, plan_digest: str
) -> SuppressionRecord | None:
    for record in read_suppression_records(control_root):
        if record.plan_digest == plan_digest:
            return record
    return None


def now_unix() -> int:
    return int(datetime.now(UTC).timestamp())


__all__ = [
    "SuppressionCoordinate",
    "SuppressionRecord",
    "find_record_by_plan_digest",
    "journal_directory",
    "now_unix",
    "read_suppression_records",
    "suppressed_coordinates",
    "suppression_identifier",
    "write_suppression_record",
]
