"""Discriminators for the standalone SQLite payload experiment."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.domain.enums import CommitStatus, MemoryDomain
from tests.support.payload_storage_probe import (
    PayloadProbeError,
    build_payload_probe,
    read_legacy_payload_manifests,
    verify_payload_probe_against,
)


@pytest.fixture
def verified_partition(tmp_path: Path) -> Path:
    with StorageAdministrationService(tmp_path / "fixture") as service:
        service.initialize()
        first = CanonicalMemoryRecord(
            memory_id="first",
            domain=MemoryDomain.TRANSCRIPT,
            text="\u00e9" * 4096,
            status=CommitStatus.COMMITTED,
        )
        second = first.model_copy(update={"memory_id": "second"})
        service.publish_memory_plane_batch((second, first))
        service.publish_memory_plane_batch((first.model_copy(update={"text": first.text + "updated"}),))
        service.acquire_verified_snapshot()
        return service.partition_path()


def test_both_variants_reconstruct_exact_catalogs_without_overwriting_source(
    tmp_path: Path,
    verified_partition: Path,
) -> None:
    manifest = read_legacy_payload_manifests(verified_partition)
    assert {entry.catalog: entry.row_count for entry in manifest.catalogs} == {
        "memory_batches": 2,
        "memory_current_records": 2,
        "memory_record_versions": 3,
    }
    for compress in (False, True):
        target = tmp_path / f"probe-{compress}.sqlite3"
        metrics = build_payload_probe(verified_partition, target, compress=compress)
        assert metrics["unique_payloads"] == 3
        assert metrics["compressed_payloads"] == (3 if compress else 0)
        assert verify_payload_probe_against(target, manifest)["manifest_digest"] == manifest.digest()
    with pytest.raises(FileExistsError):
        build_payload_probe(verified_partition, verified_partition)
    assert read_legacy_payload_manifests(verified_partition) == manifest


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ("UPDATE probe_payloads SET raw_size=raw_size-1", "invalid compressed payload extent|digest or size mismatch"),
        ("UPDATE probe_members SET ordinal=ordinal+10 WHERE revision=1", "unexpected batch member ordinal"),
        ("UPDATE probe_current SET digest=zeroblob(32)", "dangling payload or batch reference"),
        (
            "UPDATE probe_current SET digest=(SELECT digest FROM probe_versions WHERE memory_id='first' AND revision=1) "
            "WHERE memory_id='first'",
            "reconstructed materializations differ from original catalog roots",
        ),
        (
            "UPDATE probe_current SET source_kind='changed'",
            "reconstructed materializations differ from original catalog roots",
        ),
    ],
)
def test_exact_proof_rejects_corrupted_sizes_references_order_and_metadata(
    tmp_path: Path,
    verified_partition: Path,
    mutation: str,
    error: str,
) -> None:
    manifest = read_legacy_payload_manifests(verified_partition)
    target = tmp_path / "probe.sqlite3"
    build_payload_probe(verified_partition, target, compress=True)
    with closing(sqlite3.connect(target)) as connection, connection:
        connection.execute(mutation)
    with pytest.raises(PayloadProbeError, match=error):
        verify_payload_probe_against(target, manifest)
