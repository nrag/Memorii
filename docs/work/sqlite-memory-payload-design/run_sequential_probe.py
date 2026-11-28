"""Compare raw sequential verification and first point reads on audited fixtures."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter_ns

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.store import PersistedBatch, contains_runtime_context
from memorii.core.persistence.contracts import RuntimeMaterializationManifest
from memorii.core.storage_administration.service import StorageAdministrationService
from tests.support import payload_storage_probe as legacy
from tests.support import sequential_payload_probe as sequential

_WORK = Path("/work")
_MIB = 1024**2


def emit(**fields: object) -> None:
    print(json.dumps(fields, sort_keys=True), flush=True)


def first_projected_read(
    path: Path, record_id: str, expected_revisions: tuple[int, int]
) -> CanonicalMemoryRecord:
    # The verifier ran against this frozen scratch file before timing the read.
    data_revision = 0
    batch_count = 0
    with closing(legacy._read_only(path)) as connection:
        connection.execute("BEGIN")
        for batch_count, header in enumerate(
            connection.execute(
                "SELECT revision,data_revision,checksum,member_count FROM probe_batches ORDER BY revision"
            ),
            start=1,
        ):
            revision, stored_data_revision, checksum, member_count = header
            members = tuple(
                CanonicalMemoryRecord.model_validate_json(row[0])
                for row in connection.execute(
                    "SELECT p.body FROM probe_members m JOIN probe_payloads p USING(digest) "
                    "WHERE m.revision=? ORDER BY m.ordinal",
                    (revision,),
                )
            )
            data_revision += int(contains_runtime_context(members))
            if (revision, stored_data_revision, member_count) != (batch_count, data_revision, len(members)):
                raise legacy.PayloadProbeError("projected batch revision or member count differs")
            # This validator recomputes the original sorted, semantic batch checksum.
            PersistedBatch(revision=revision, data_revision=data_revision, records=members, checksum=checksum)
        if (batch_count, data_revision) != expected_revisions:
            raise legacy.PayloadProbeError("projected memory revision state differs")
        current = connection.execute(
            "SELECT p.body FROM probe_current c JOIN probe_payloads p USING(digest) WHERE c.memory_id=?",
            (record_id,),
        ).fetchone()
        if current is None:
            raise legacy.PayloadProbeError("expected current record is missing")
        return CanonicalMemoryRecord.model_validate_json(current[0])


def baseline_sample(root: Path, expected_tuple: str):
    with StorageAdministrationService(root) as service:
        started = perf_counter_ns()
        verified = service.acquire_verified_snapshot()
        acquire_ns = perf_counter_ns() - started
        if verified.tuple_digest != expected_tuple:
            raise legacy.PayloadProbeError("fixture tuple differs")
        source = service.partition_path()
        with service.partition().transaction(write=False) as connection:
            current = connection.execute(
                "SELECT memory_id FROM memory_current_records WHERE source_kind='semantic_ingestion_source' "
                "ORDER BY memory_id LIMIT 1"
            ).fetchone()
        if current is None or not isinstance(current[0], str):
            raise legacy.PayloadProbeError("native fixture record is missing")
        record_id = current[0]
        backend = service.memory_plane_store()
        started = perf_counter_ns()
        expected_record = backend.get_record(record_id)
        first_ns = perf_counter_ns() - started
        started = perf_counter_ns()
        repeated = backend.get_record(record_id)
        repeat_ns = perf_counter_ns() - started
        if expected_record is None or repeated != expected_record:
            raise legacy.PayloadProbeError("baseline reads differ")
        return (acquire_ns, first_ns, repeat_ns), verified, source, record_id, expected_record


def measure(size: int, expected_tuple: str) -> None:
    root = _WORK / f"baseline-{size}"
    timings, verified, source, record_id, expected_record = baseline_sample(root, expected_tuple)
    samples = [timings]
    for _ in range(2):
        timings, *identity = baseline_sample(root, expected_tuple)
        if tuple(identity) != (verified, source, record_id, expected_record):
            raise legacy.PayloadProbeError("baseline sample differs")
        samples.append(timings)
    acquire_samples, read_samples, repeat_samples = zip(*samples, strict=True)
    revisions = verified.vector.memory_write_revision, verified.vector.memory_data_revision
    emit(
        type="baseline", size=size, tuple_digest=verified.tuple_digest, signed_manifest=verified.manifest_digest,
        acquire_samples_ns=acquire_samples, first_read_samples_ns=read_samples, repeat_samples_ns=repeat_samples,
    )
    with TemporaryDirectory(dir=_WORK) as folder:
        legacy_scratch = Path(folder) / "legacy_probe.db"
        raw = Path(folder) / "sequential.db"
        legacy.build_payload_probe(source, legacy_scratch)
        with StorageAdministrationService(root) as service:
            current = service.acquire_verified_snapshot()
            if current != verified:
                raise legacy.PayloadProbeError("signed source changed during the diagnostic")
            with service.partition().transaction(write=False) as connection:
                all_entries = service.partition().compute_materialization_manifest(connection)
            if RuntimeMaterializationManifest(catalogs=all_entries).digest() != verified.manifest_digest:
                raise legacy.PayloadProbeError("recomputed manifest differs from signed manifest")
        expected_legacy = RuntimeMaterializationManifest(
            catalogs=tuple(entry for entry in all_entries if entry.catalog in legacy._CATALOGS)
        )
        expected_projection = sequential.build_sequential_projection(legacy_scratch, raw)
        legacy_scratch.unlink()
        legacy.verify_payload_probe_against(raw, expected_legacy)
        projection_bytes = raw.stat().st_size
        scan_results = {}
        scan_modes: tuple[sequential.ReadMode, ...] = ("select", "blob")
        variants: list[tuple[sequential.ReadMode, int]] = [(mode, mmap) for mmap in (0, 1024 * _MIB) for mode in scan_modes]
        for mode, mmap in variants:
            samples = []
            for _ in range(3):
                started = perf_counter_ns()
                sequential.verify_sequential_projection(raw, expected_projection, read_mode=mode, mmap_bytes=mmap)
                samples.append(perf_counter_ns() - started)
            scan_results[f"{mode}:{mmap}"] = samples
        projected_reads = []
        for _ in range(3):
            started = perf_counter_ns()
            projected = first_projected_read(raw, record_id, revisions)
            projected_reads.append(perf_counter_ns() - started)
            if projected != expected_record:
                raise legacy.PayloadProbeError("projected point read differs")
        emit(
            type="sequential", size=size, projection_bytes=projection_bytes,
            v7_manifest=expected_legacy.digest(), projected_manifest=expected_projection.digest(),
            scan_samples_ns=scan_results, first_read_samples_ns=projected_reads,
        )


def main() -> None:
    script = Path(__file__)
    emit(
        type="identity", sqlite=sqlite3.sqlite_version,
        runner_hash=hashlib.sha256(script.read_bytes()).hexdigest(),
        probe_hash=hashlib.sha256(Path(sequential.__file__).read_bytes()).hexdigest(),
    )
    for line in script.with_name("fixtures.jsonl").read_text().splitlines():
        fixture = json.loads(line)
        if fixture["type"] == "fixture":
            measure(fixture["source_count"], fixture["partition_tuple_digest"])


if __name__ == "__main__":
    main()
