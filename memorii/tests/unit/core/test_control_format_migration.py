"""Control-format migration journeys: plan/apply, crash cuts, downgrade rules."""
from __future__ import annotations

from pathlib import Path

import pytest
from memorii.core.storage_administration.control_migration import (
    ControlMigrationError,
    migrate_control_format,
    plan_control_format_migration,
    read_control_schema_version,
    require_control_format,
)
from memorii.core.storage_administration.service import (
    StorageAdministrationService,
)
from memorii.stores.sqlite.control import ControlStateError


def _installation(tmp_path: Path) -> Path:
    service = StorageAdministrationService(tmp_path / "installation")
    service.initialize()
    service.close()
    return tmp_path / "installation"


def test_plan_and_apply_migrate_one_version_with_pointer(tmp_path: Path) -> None:
    root = _installation(tmp_path)
    control = root / "control" / "control.sqlite3"
    assert read_control_schema_version(control) == 1

    plan = plan_control_format_migration(control, target_version=2)
    assert plan.source_version == 1
    assert plan.target_version == 2
    assert plan.control_database_digest

    receipt = migrate_control_format(
        control, target_version=2, keys_directory=root / "control" / "keys"
    )
    assert receipt.plan == plan
    pointer = root / "control" / "control-generations" / "control-generation.json"
    import json

    record = json.loads(pointer.read_text())
    assert record["source_version"] == 1
    assert record["target_version"] == 2
    assert record["target_digest"]
    # The staged generation carries the new version; the source is retained.
    staged = root / "control" / "control-generations" / "control.v2.sqlite3"
    assert read_control_schema_version(staged) == 2
    assert read_control_schema_version(control) == 1


def test_unknown_and_multi_step_formats_reject_before_writes(tmp_path: Path) -> None:
    root = _installation(tmp_path)
    control = root / "control" / "control.sqlite3"
    with pytest.raises(ControlMigrationError, match="unknown control format"):
        plan_control_format_migration(control, target_version=99)
    # Multi-step rejection: after one migration the source is v2; v3 is a
    # known future format beyond this binary's supported set, but a v1
    # source asked for v3 reports the step violation distinctly.
    with pytest.raises(ControlMigrationError, match="unknown control format 3"):
        plan_control_format_migration(control, target_version=3)
    migrate_control_format(
        control, target_version=2, keys_directory=root / "control" / "keys"
    )
    staged = root / "control" / "control-generations" / "control.v2.sqlite3"
    with pytest.raises(ControlMigrationError, match="unknown control format"):
        plan_control_format_migration(staged, target_version=3)


def test_downgrade_refuses_after_newer_generation(tmp_path: Path) -> None:
    root = _installation(tmp_path)
    control = root / "control" / "control.sqlite3"
    migrate_control_format(
        control, target_version=2, keys_directory=root / "control" / "keys"
    )
    # A binary supporting only version 1 refuses the v2 generation.
    staged = root / "control" / "control-generations" / "control.v2.sqlite3"
    with pytest.raises(ControlStateError, match="refusing downgrade"):
        require_control_format(staged, maximum_supported=1)
    # A binary supporting v2 accepts it.
    require_control_format(staged, maximum_supported=2)


def test_pending_intent_blocks_migration(tmp_path: Path) -> None:
    root = _installation(tmp_path)
    control = root / "control" / "control.sqlite3"
    import sqlite3

    connection = sqlite3.connect(control)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO publication_intents (repository_id, intent_json)"
            " VALUES ('r:test', '{\"phase\": \"prepared\"}')"
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(ControlMigrationError, match="prepared publication intent"):
        migrate_control_format(
            control, target_version=2, keys_directory=root / "control" / "keys"
        )
