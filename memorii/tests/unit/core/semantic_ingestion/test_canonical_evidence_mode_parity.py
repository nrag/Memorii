"""Diametric canonical-evidence mode-parity proofs.

Every node here runs the same scenario through the two opposed modes — the
default substituted path and the explicitly disabled full-validation path —
and requires identical public outcomes, idempotence, and durable structural
projections.  These are the slow cadence gate for the enable-by-default
decision of 2026-08-27; every other test in the repository runs with the
substitution enabled.
"""

from __future__ import annotations

from pathlib import Path

from memorii.core.memory_plane.store import JsonlMemoryPlaneStore
from memorii.core.memory_plane.service import MemoryPlaneService

from tests.unit.core.semantic_ingestion.test_bootstrap_graph_coordinator_v3 import (
    _delivery,
    _interrupt_after_handoff,
    _production_recovery_service,
    _scenario_recovery_service,
)


def _durable_projection(plane: MemoryPlaneService) -> dict[str, object]:
    projection: dict[str, object] = {}
    for record in plane.list_records():
        projection.setdefault(record.source_kind, 0)
        projection[record.source_kind] += 1
    return projection


def test_redelivery_recovery_outcomes_are_identical_across_enabled_and_disabled_modes(
    monkeypatch, tmp_path: Path,
) -> None:
    enabled_plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(tmp_path / "enabled")
    )
    disabled_plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(tmp_path / "disabled")
    )
    enabled_service = _production_recovery_service(plane=enabled_plane)
    disabled_service = _scenario_recovery_service(plane=disabled_plane)
    _interrupt_after_handoff(monkeypatch, enabled_service, "recovery-mode-parity")
    _interrupt_after_handoff(monkeypatch, disabled_service, "recovery-mode-parity")

    enabled_recovered = _delivery(enabled_service, "recovery-mode-parity")
    disabled_recovered = _delivery(disabled_service, "recovery-mode-parity")
    assert (
        enabled_recovered.blocked_reasons["semantic_ingestion"]
        == disabled_recovered.blocked_reasons["semantic_ingestion"]
        == "source_only"
    )
    enabled_again = _delivery(enabled_service, "recovery-mode-parity")
    disabled_again = _delivery(disabled_service, "recovery-mode-parity")
    assert enabled_again == enabled_recovered
    assert disabled_again == disabled_recovered

    # Record bytes embed material-derived identities (source ids, preparation
    # fingerprints), so cross-material byte equality is not a well-formed
    # claim; structural, outcome, and idempotence parity carry the
    # mode-equivalence projection, and byte-level substitution equality is
    # proven inside the lease consumers of the sibling recovery proofs.
    assert _durable_projection(enabled_plane) == _durable_projection(disabled_plane)
    enabled_index = enabled_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_v3_recovery_index"
    )[0].content
    disabled_index = disabled_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_v3_recovery_index"
    )[0].content
    assert enabled_index["state"] == disabled_index["state"] == "found"


def test_direct_delivery_outcomes_are_identical_across_enabled_and_disabled_modes(
    tmp_path: Path,
) -> None:
    enabled_plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(tmp_path / "direct-enabled")
    )
    disabled_plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(tmp_path / "direct-disabled")
    )
    enabled_service = _production_recovery_service(plane=enabled_plane)
    disabled_service = _scenario_recovery_service(plane=disabled_plane)

    enabled_result = _delivery(enabled_service, "direct-mode-parity")
    disabled_result = _delivery(disabled_service, "direct-mode-parity")
    assert (
        enabled_result.blocked_reasons["semantic_ingestion"]
        == disabled_result.blocked_reasons["semantic_ingestion"]
    )
    enabled_idempotent = _delivery(enabled_service, "direct-mode-parity")
    disabled_idempotent = _delivery(disabled_service, "direct-mode-parity")
    assert enabled_idempotent == enabled_result
    assert disabled_idempotent == disabled_result
    assert _durable_projection(enabled_plane) == _durable_projection(disabled_plane)
