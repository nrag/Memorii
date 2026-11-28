"""Measure the standalone projection over prebuilt signed Linux diagnostics."""

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter_ns

from memorii.core.persistence.contracts import RuntimeMaterializationManifest
from memorii.core.storage_administration.service import StorageAdministrationService
from tests.support import payload_storage_probe as probe

_WORK = Path("/work")


def copy_samples(path: Path) -> list[int]:
    samples = []
    for _ in range(3):
        with (
            TemporaryDirectory(dir=_WORK) as folder,
            closing(probe._read_only(path)) as src,
            closing(sqlite3.connect(Path(folder) / "copy.db")) as dst,
        ):
            started = perf_counter_ns()
            src.backup(dst)
            samples.append(perf_counter_ns() - started)
    return samples


def scan_samples(path: Path) -> list[int]:
    times = []
    for _ in range(3):
        started = perf_counter_ns()
        with closing(probe._read_only(path)) as connection:
            connection.execute("BEGIN")
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise probe.PayloadProbeError("payload reference check failed")
            for row in connection.execute("SELECT * FROM probe_payloads ORDER BY digest"):
                probe._load_payload(row)
        times.append(perf_counter_ns() - started)
    return times


def emit(**fields: object) -> None:
    print(json.dumps(fields, sort_keys=True), flush=True)


def measure_fixture(size: int, expected_tuple: str, expected_bytes: int) -> None:
    started = perf_counter_ns()
    with StorageAdministrationService(_WORK / f"baseline-{size}") as service:
        verified = service.acquire_verified_snapshot()
        source = service.partition_path()
        acquire_ns = perf_counter_ns() - started
        if verified.tuple_digest != expected_tuple or source.stat().st_size != expected_bytes:
            raise probe.PayloadProbeError("fixture identity differs from its audit")
        with service.partition().transaction(write=False) as connection:
            catalog_entries = service.partition().compute_materialization_manifest(connection)
        if RuntimeMaterializationManifest(catalogs=catalog_entries).digest() != verified.manifest_digest:
            raise probe.PayloadProbeError("source catalog commitments differ from signed manifest")
    started = perf_counter_ns()
    expected = probe.read_legacy_payload_manifests(source)
    source_scan_ns = perf_counter_ns() - started
    expected_catalogs = {entry.catalog for entry in expected.catalogs}
    if tuple(entry for entry in catalog_entries if entry.catalog in expected_catalogs) != expected.catalogs:
        raise probe.PayloadProbeError("original payload catalog commitments differ")
    emit(
        type="baseline", size=size, tuple_digest=verified.tuple_digest, signed_manifest=verified.manifest_digest,
        compatible_manifest=expected.digest(), source_bytes=expected_bytes, fresh_acquire_ns=acquire_ns,
        source_scan_ns=source_scan_ns, copy_samples_ns=copy_samples(source),
    )
    for compressed in (False, True):
        with TemporaryDirectory(dir=_WORK) as folder:
            projection = Path(folder) / "probe.db"
            result = probe.build_payload_probe(source, projection, compress=compressed)
            parity = probe.verify_payload_probe_against(projection, expected)
            emit(
                type="probe", size=size, **result, **parity, copy_samples_ns=copy_samples(projection),
                unique_scan_samples_ns=scan_samples(projection),
            )


def main() -> None:
    runner = Path(__file__)
    emit(
        type="identity", sqlite=sqlite3.sqlite_version,
        runner_hash=hashlib.sha256(runner.read_bytes()).hexdigest(),
        probe_hash=hashlib.sha256(Path(probe.__file__).read_bytes()).hexdigest(),
    )
    for line in runner.with_name("fixtures.jsonl").read_text().splitlines():
        fixture = json.loads(line)
        if fixture["type"] == "fixture":
            measure_fixture(fixture["source_count"], fixture["partition_tuple_digest"], fixture["database_bytes"])


if __name__ == "__main__":
    main()
