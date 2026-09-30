"""Operator controls: owner capability, modes, status, export."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from memorii.core.persistence.contracts import canonical_json_digest
from memorii.core.persistence.runtime_contracts import TaskRecord
from memorii.core.persistence.runtime_repository import (
    publish_runtime_change,
)
from memorii.core.storage_administration.operator import (
    ModeChangeRequest,
    OperatorError,
    OwnerCapability,
    StorageAdministrationOperator,
)
from memorii.core.storage_administration.service import StorageAdministrationService

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _operator(tmp_path: Path) -> tuple[StorageAdministrationOperator, StorageAdministrationService]:
    service = StorageAdministrationService(tmp_path / "installation")
    service.initialize()
    return StorageAdministrationOperator(service), service


def _capability(service: StorageAdministrationService) -> OwnerCapability:
    return OwnerCapability(
        owner_principal="owner:one",
        capability_digest=canonical_json_digest(
            {
                "installation_id": service._control_state().installation_id,
                "owner_principal": "owner:one",
            }
        ),
    )


def test_status_reports_content_free_state(tmp_path: Path) -> None:
    operator, service = _operator(tmp_path)
    try:
        status = operator.status()
        assert status.mode == "active"
        assert status.quarantined is False
        assert status.runtime_revision == 0
        assert status.memory_write_revision == 0
    finally:
        service.close()


def test_mode_change_fences_and_round_trips(tmp_path: Path) -> None:
    operator, service = _operator(tmp_path)
    try:
        capability = _capability(service)
        paused = operator.change_mode(
            ModeChangeRequest(
                target_mode="read_only",
                expected_control_revision=service._control_state().control_revision,
                reason="maintenance window",
            ),
            capability=capability,
        )
        assert paused.mode == "read_only"
        # Data publication is fenced in read_only.
        from memorii.core.storage_administration.service import (
            InstallationQuarantinedError,
        )

        with pytest.raises(InstallationQuarantinedError, match="read_only"):
            publish_runtime_change(
                service, lambda connection, repository: None
            )
        resumed = operator.change_mode(
            ModeChangeRequest(
                target_mode="active",
                expected_control_revision=service._control_state().control_revision,
                reason="maintenance complete",
            ),
            capability=capability,
        )
        assert resumed.mode == "active"
        revision = publish_runtime_change(
            service, lambda connection, repository: None
        )
        assert revision >= 1
    finally:
        service.close()


def test_stale_control_revision_conflicts(tmp_path: Path) -> None:
    operator, service = _operator(tmp_path)
    try:
        with pytest.raises(OperatorError, match="control revision changed"):
            operator.change_mode(
                ModeChangeRequest(
                    target_mode="read_only",
                    expected_control_revision=99,
                    reason="stale",
                ),
                capability=_capability(service),
            )
    finally:
        service.close()


def test_foreign_capability_denies_before_state_change(tmp_path: Path) -> None:
    operator, service = _operator(tmp_path)
    try:
        forged = OwnerCapability(
            owner_principal="owner:other",
            capability_digest="0" * 64,
        )
        with pytest.raises(OperatorError, match="does not match"):
            operator.change_mode(
                ModeChangeRequest(
                    target_mode="read_only",
                    expected_control_revision=service._control_state().control_revision,
                    reason="forged",
                ),
                capability=forged,
            )
        assert service._control_state().mode == "active"
    finally:
        service.close()


def test_bypass_returns_to_active_only(tmp_path: Path) -> None:
    operator, service = _operator(tmp_path)
    try:
        capability = _capability(service)
        bypassed = operator.change_mode(
            ModeChangeRequest(
                target_mode="bypass",
                expected_control_revision=service._control_state().control_revision,
                reason="host stop calling data paths",
            ),
            capability=capability,
        )
        assert bypassed.mode == "bypass"
        with pytest.raises(OperatorError, match="bypass returns to active only"):
            operator.change_mode(
                ModeChangeRequest(
                    target_mode="read_only",
                    expected_control_revision=service._control_state().control_revision,
                    reason="invalid transition",
                ),
                capability=capability,
            )
        returned = operator.change_mode(
            ModeChangeRequest(
                target_mode="active",
                expected_control_revision=service._control_state().control_revision,
                reason="return to active",
            ),
            capability=capability,
        )
        assert returned.mode == "active"
    finally:
        service.close()


def test_export_is_scoped_deterministic_and_authorized(tmp_path: Path) -> None:
    operator, service = _operator(tmp_path)
    try:
        publish_runtime_change(
            service,
            lambda connection, repository: repository.apply_task(
                connection,
                TaskRecord(
                    task_id="task:export",
                    principal="principal:a",
                    goal="Export journey",
                    created_at=_NOW,
                    root_execution_node_id="exec:root",
                ),
            ),
        )
        export = operator.read_export(capability=_capability(service))
        assert export["tasks"][0]["task_id"] == "task:export"
        assert export["memory_data_revision"] == 0
        forged = OwnerCapability(
            owner_principal="owner:other", capability_digest="1" * 64
        )
        with pytest.raises(OperatorError, match="does not match"):
            operator.read_export(capability=forged)
    finally:
        service.close()
