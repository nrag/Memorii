"""Coverage for sequential payload and reference verification."""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Literal

import pytest
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.persistence.contracts import RuntimeMaterializationManifest
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.domain.enums import CommitStatus, MemoryDomain
from tests.support.payload_storage_probe import (
    PayloadProbeError,
    build_payload_probe,
    read_legacy_payload_manifests,
    verify_payload_probe_against,
)
from tests.support.sequential_payload_probe import build_sequential_projection, verify_sequential_projection


def _build_projection(
    tmp_path: Path, batches: tuple[tuple[CanonicalMemoryRecord, ...], ...],
) -> tuple[Path, RuntimeMaterializationManifest, RuntimeMaterializationManifest]:
    with StorageAdministrationService(tmp_path / "installation") as service:
        service.initialize()
        for records in batches:
            service.publish_memory_plane_batch(records)
        service.acquire_verified_snapshot()
        source = service.partition_path()

    legacy_manifest = read_legacy_payload_manifests(source)
    raw = tmp_path / "raw.sqlite3"
    build_payload_probe(source, raw)
    projected = tmp_path / "sequential.sqlite3"
    expected_manifest = build_sequential_projection(raw, projected)
    return projected, expected_manifest, legacy_manifest


def _record(text: str) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id="source",
        domain=MemoryDomain.TRANSCRIPT,
        text=text,
        status=CommitStatus.COMMITTED,
    )


@pytest.fixture
def sequential_projection(
    tmp_path: Path,
) -> tuple[Path, RuntimeMaterializationManifest, RuntimeMaterializationManifest]:
    record = _record("\u00e9" * 4096)
    sibling = record.model_copy(update={"memory_id": "sibling"})
    updated = record.model_copy(update={"text": record.text + " updated"})
    return _build_projection(tmp_path, ((record, sibling), (updated,)))


@pytest.mark.parametrize("read_mode", ["select", "blob"])
def test_sequential_projection_recovers_original_catalogs(
    sequential_projection: tuple[Path, RuntimeMaterializationManifest, RuntimeMaterializationManifest],
    read_mode: Literal["select", "blob"],
) -> None:
    projected, expected, legacy = sequential_projection
    verify_sequential_projection(projected, expected, read_mode=read_mode)
    assert verify_payload_probe_against(projected, legacy)["manifest_digest"] == legacy.digest()


@pytest.mark.parametrize("read_mode", ["select", "blob"])
def test_sequential_projection_rejects_equal_length_body_mutation(
    sequential_projection: tuple[Path, RuntimeMaterializationManifest, RuntimeMaterializationManifest],
    read_mode: Literal["select", "blob"],
) -> None:
    projected, expected, _ = sequential_projection
    with closing(sqlite3.connect(projected)) as connection, connection:
        connection.execute("UPDATE probe_payloads SET body=zeroblob(length(body))")
    with pytest.raises(PayloadProbeError, match="payload digest"):
        verify_sequential_projection(projected, expected, read_mode=read_mode)


@pytest.mark.parametrize(
    "mutation",
    [
        "UPDATE probe_current SET digest=(SELECT digest FROM probe_versions WHERE memory_id='source' AND revision=1) "
        "WHERE memory_id='source'",
        "UPDATE probe_members SET ordinal=ordinal+10 WHERE revision=1 AND ordinal=0",
        "UPDATE probe_current SET source_kind='changed' WHERE memory_id='source'",
        "UPDATE probe_current SET digest=zeroblob(32) WHERE memory_id='source'",
    ],
)
def test_sequential_projection_rejects_reference_drift_with_untouched_bodies(
    sequential_projection: tuple[Path, RuntimeMaterializationManifest, RuntimeMaterializationManifest],
    mutation: str,
) -> None:
    projected, expected, _ = sequential_projection
    with closing(sqlite3.connect(projected)) as connection, connection:
        connection.execute(mutation)
    with pytest.raises(PayloadProbeError, match="projected catalog commitments differ"):
        verify_sequential_projection(projected, expected)


@pytest.mark.parametrize("read_mode", ["select", "blob"])
@pytest.mark.parametrize(
    ("index_only", "error"),
    [(False, "projected catalog commitments differ"), (True, "payload digest index differs")],
)
def test_sequential_projection_rejects_disagreement_between_payload_and_index_pages(
    tmp_path: Path,
    read_mode: Literal["select", "blob"],
    index_only: bool,
    error: str,
) -> None:
    original_text = "unaltered payload marker"
    projected, expected, _ = _build_projection(tmp_path, ((_record(original_text),),))
    verify_sequential_projection(projected, expected, read_mode=read_mode)

    with closing(sqlite3.connect(projected)) as connection:
        digest, body = connection.execute("SELECT digest,body FROM probe_payloads NOT INDEXED").fetchone()
        page_size = connection.execute("PRAGMA page_size").fetchone()[0]
        target = "probe_payloads"
        if index_only:
            target = connection.execute(
                "SELECT name FROM pragma_index_list('probe_payloads') WHERE origin='pk'",
            ).fetchone()[0]
        root_page = connection.execute(
            "SELECT rootpage FROM sqlite_schema WHERE name=?", (target,),
        ).fetchone()[0]
    patched_body = body.replace(original_text.encode(), original_text.upper().encode())
    assert body.count(original_text.encode()) == 1
    replacement_digest = hashlib.sha256(patched_body).digest()

    offset = (root_page - 1) * page_size
    with projected.open("r+b") as file:
        file.seek(offset)
        page = file.read(page_size)
        assert page[0] == (0x0A if index_only else 0x0D)
        assert page.count(digest) == 1
        patched_page = page.replace(digest, replacement_digest)
        if not index_only:
            assert patched_page.count(body) == 1
            patched_page = patched_page.replace(body, patched_body)
        assert len(patched_page) == page_size
        file.seek(offset)
        file.write(patched_page)

    with pytest.raises(PayloadProbeError, match=error):
        verify_sequential_projection(projected, expected, read_mode=read_mode)
