"""Legacy migration planning: read-only, fail-closed, digest-bound."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore
from memorii.core.storage_administration.migration import (
    LegacyMigrationError,
    LegacyStorageSelector,
    MemoryPlaneMigrationPlan,
    build_migration_plan,
)
from memorii.domain.enums import CommitStatus, MemoryDomain


def _seed_legacy_plane(root: Path, batches: int = 3) -> Path:
    plane = root / "memory_plane"
    store = JsonlMemoryPlaneStore(plane)
    for index in range(batches):
        store.write_records(
            (
                CanonicalMemoryRecord(
                    memory_id=f"mem:legacy:{index}",
                    domain=MemoryDomain.SEMANTIC,
                    text=f"legacy:{index}",
                    status=CommitStatus.COMMITTED,
                    source_kind="legacy_migration_test",
                    timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                ),
            )
        )
    return plane


def test_plan_is_read_only_and_digest_bound(tmp_path: Path) -> None:
    plane = _seed_legacy_plane(tmp_path)
    before = (plane / "memory_records.jsonl").read_bytes()
    plan = build_migration_plan(tmp_path, plane_directory=plane)
    assert (plane / "memory_records.jsonl").read_bytes() == before
    assert plan.batch_count == 3
    assert plan.record_count == 3
    assert plan.write_revision == 3
    assert plan.data_revision == 3
    assert plan.target_format == "sqlite"
    with pytest.raises(ValueError):
        MemoryPlaneMigrationPlan.model_validate(
            plan.model_dump(mode="json") | {"records_size": plan.records_size + 1}
        )


def test_plan_inventories_participants(tmp_path: Path) -> None:
    plane = _seed_legacy_plane(tmp_path)
    (tmp_path / "work_state").mkdir()
    (tmp_path / "semantic_integrity").mkdir()
    plan = build_migration_plan(tmp_path, plane_directory=plane)
    assert "work_state" in plan.participant_inventory
    assert "semantic_integrity" in plan.participant_inventory
    assert "decision_state" not in plan.participant_inventory


def test_plan_refuses_unknown_plane_members(tmp_path: Path) -> None:
    plane = _seed_legacy_plane(tmp_path)
    (plane / "stranger.jsonl").write_text("{}", encoding="utf-8")
    with pytest.raises(LegacyMigrationError, match="unsupported_configuration"):
        build_migration_plan(tmp_path, plane_directory=plane)


def test_plan_refuses_missing_plane(tmp_path: Path) -> None:
    with pytest.raises(LegacyMigrationError, match="migration_required"):
        build_migration_plan(tmp_path, plane_directory=tmp_path / "memory_plane")


def test_plan_fails_closed_on_corrupt_chain(tmp_path: Path) -> None:
    plane = _seed_legacy_plane(tmp_path)
    records_path = plane / "memory_records.jsonl"
    records_path.write_text(records_path.read_text() + "corrupt\n", encoding="utf-8")
    with pytest.raises(Exception, match="invalid memory-plane batch|incomplete batch"):
        build_migration_plan(tmp_path, plane_directory=plane)


def test_legacy_storage_selector_digest_is_stable(tmp_path: Path) -> None:
    plane = _seed_legacy_plane(tmp_path)
    plan = build_migration_plan(tmp_path, plane_directory=plane)
    selector = LegacyStorageSelector(
        installation_root=str(tmp_path),
        plane_directory=str(plane),
        records_digest=plan.records_digest,
        records_size=plan.records_size,
        write_revision=plan.write_revision,
        data_revision=plan.data_revision,
        plan_digest=plan.plan_digest,
    )
    assert selector.selector_digest() == selector.model_copy(
        update={
            "installation_root": str(tmp_path),
        }
    ).selector_digest()
    assert selector.discriminator == "legacy_jsonl"
    # model_copy bypasses validation by design; the closed schema is enforced
    # at parse boundaries:
    with pytest.raises(ValueError):
        LegacyStorageSelector.model_validate(
            selector.model_dump(mode="json") | {"records_digest": "f" * 63}
        )
