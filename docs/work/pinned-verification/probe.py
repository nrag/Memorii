"""Measure a managed writer overlapping exact verification on synthetic copies."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing, contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Event
from time import monotonic_ns

from memorii.core.memory_plane.file_lock import locked_file
from memorii.core.persistence.contracts import InstallationControlState, RuntimePublicationState
from memorii.core.persistence.key_owner import LocalSigningKeyOwner
from memorii.core.storage_administration.operator_backup import _open_backup_snapshot
from memorii.core.storage_administration.service import (
    InstallationIntegrityError,
    PartitionVerificationSnapshot,
    StorageAdministrationError,
    StorageAdministrationService,
)
from memorii.stores.sqlite.partition import PartitionDataRepository, VerificationCookie
from tests.support.reference_capacity import Distribution, warm_samples
from tests.support.reference_capacity_fixture import _installed_wheel_digest
from tests.support.reference_capacity_measure import _fresh_copy, _WarmRuntime


@dataclass(frozen=True)
class Authority:
    state: InstallationControlState
    publication: RuntimePublicationState
    path: Path
    data_identity: tuple[int, int]
    control_identity: tuple[int, int]
    journal_tip: tuple[int, str]
    signer: str


def authority(service: StorageAdministrationService) -> Authority:
    state = service._require_operational()
    path, publication = service._active_partition_selection()
    if publication is None or service._control.read_pending_intent(publication.repository_id) is not None:
        raise StorageAdministrationError("probe requires a stable named partition")
    signer = LocalSigningKeyOwner(service.installation_root / "control" / "keys").public_key_fingerprint(
        service._signer_key_id,
    )
    if signer != service._signing.public_key_fingerprint(service._signer_key_id):
        raise InstallationIntegrityError("cached signer differs from current owner")
    return Authority(
        state, publication, path, service._partition_file_identity(path),
        service._partition_file_identity(service.control_path()), service._control.next_journal_position(), signer,
    )


def checked_row(service: StorageAdministrationService, connection: sqlite3.Connection, pin: Authority) -> None:
    partition = service.partition()
    row = partition.read_publication_row(connection)
    if row is None or (
        row["tuple_digest"] != pin.publication.payload_digest()
        or not service._matches_signed_publication(row, pin.publication)
        or partition.read_revision_state(connection) != (
            pin.publication.vector.memory_write_revision, pin.publication.vector.memory_data_revision,
        )
    ):
        raise InstallationIntegrityError("snapshot row differs from signed publication")


def pinned_acquisition(
    service: ObservedService, *, before_revalidation: Callable[[], None] | None = None,
) -> PartitionVerificationSnapshot:
    for _ in range(3):
        with ExitStack() as stack:
            with service._publication_fence():
                pin = authority(service)
                partition = service.partition()
                if partition.database_path != pin.path:
                    raise InstallationIntegrityError("selected partition changed")
                with locked_file(pin.path.with_name(pin.path.name + ".lock"), exclusive=False):
                    observer = stack.enter_context(closing(sqlite3.connect(pin.path.as_uri() + "?mode=ro", uri=True)))
                    observer.row_factory = sqlite3.Row
                    cookie: VerificationCookie = partition.verification_cookie(observer)
                    data = stack.enter_context(_open_backup_snapshot(pin.path))
                    checked_row(service, data, pin)
                    if not partition.uses_raw_memory_payloads(data):
                        raise StorageAdministrationError("probe requires staged raw payload storage")
                    if authority(service) != pin or partition.verification_cookie(observer) != cookie:
                        service.stale += 1
                        continue

            verified = service._matches_materialization(data, pin.publication, partition=partition)
            if before_revalidation is not None:
                before_revalidation()

            with service._publication_fence(), locked_file(
                pin.path.with_name(pin.path.name + ".lock"), exclusive=False,
            ):
                if authority(service) != pin or partition.verification_cookie(observer) != cookie:
                    service.stale += 1
                    continue
                checked_row(service, observer, pin)
                if partition.verification_cookie(observer) != cookie:
                    service.stale += 1
                    continue
                if not verified:
                    raise InstallationIntegrityError("current pinned snapshot failed exact verification")
                publication = pin.publication
                return PartitionVerificationSnapshot(
                    tuple_digest=publication.payload_digest(), ordinal=publication.vector.partition_ordinal,
                    manifest_digest=publication.manifest_digest, vector=publication.vector,
                )
    raise StorageAdministrationError("current publication changed during all pinned verification attempts")


class ObservedService(StorageAdministrationService):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.fences: list[tuple[int, int]] = []
        self.scans: list[tuple[int, int]] = []
        self.scan_started: Event | None = None
        self.writer_arrived: Event | None = None
        self.stale = 0

    @contextmanager
    def _publication_fence(self) -> Iterator[None]:
        started = monotonic_ns()
        if self.writer_arrived is not None and self.scan_started is None:
            self.writer_arrived.set()
        with super()._publication_fence():
            entered = monotonic_ns()
            try:
                yield
            finally:
                self.fences.append((entered - started, monotonic_ns() - entered))

    def _matches_materialization(
        self, connection: sqlite3.Connection, finalized: RuntimePublicationState, *,
        partition: PartitionDataRepository | None = None, cookie: VerificationCookie | None = None,
    ) -> bool:
        started = monotonic_ns()
        if self.scan_started is not None and not self.scans:
            self.scan_started.set()
            if self.writer_arrived is None or not self.writer_arrived.wait(30):
                raise TimeoutError("writer never attempted its fence")
        try:
            return super()._matches_materialization(connection, finalized, partition=partition, cookie=cookie)
        finally:
            self.scans.append((started, monotonic_ns()))


def trial(
    base: Path, work: Path, distribution: Distribution, expected: str, use_pin: bool, *, warm_writer_manifest: bool,
) -> dict[str, object]:
    with (
        _fresh_copy(base, work) as root,
        ObservedService(root) as reader,
        ObservedService(root) as writer,
    ):
        runtime = _WarmRuntime(writer, distribution, label="background")
        command = next(warm_samples(distribution, "command_commit", contended=True))
        if writer.acquire_verified_snapshot().tuple_digest != expected:
            raise RuntimeError("fixture does not match qualification")
        runtime.prepare_commands(command)
        with writer._publication_fence():
            publication = authority(writer).publication
            if publication.payload_digest() != expected:
                raise RuntimeError("writer setup changed the signed input tuple")
            partition = writer.partition()
            with partition.manual_write_transaction() as handle:
                if warm_writer_manifest:
                    writer._require_materialization_base(handle.connection, publication)
                cached = partition.has_verified_manifest_base(handle.connection, publication.manifest_digest)
        if warm_writer_manifest and not cached:
            raise RuntimeError("writer does not have its exact verified manifest base")
        writer.fences.clear()
        writer.scans.clear()
        started, arrived, write_finished = Event(), Event(), Event()
        reader.scan_started = started
        reader.writer_arrived = writer.writer_arrived = arrived
        coordination_wait_ns = 0

        def write() -> tuple[int, int, object]:
            if not started.wait(30):
                raise TimeoutError("reader never started exact verification")
            start = monotonic_ns()
            try:
                result = runtime.process(command)
                end = monotonic_ns()
                if result.error is not None:
                    raise RuntimeError(result.error)
                return start, end, asdict(result)
            finally:
                write_finished.set()

        def await_writer_before_revalidation() -> None:
            nonlocal coordination_wait_ns
            before = monotonic_ns()
            if not write_finished.wait(60):
                raise TimeoutError("overlapping writer did not finish")
            coordination_wait_ns += monotonic_ns() - before

        with ThreadPoolExecutor(1) as executor:
            pending = executor.submit(write)
            reader_start = monotonic_ns()
            result = (
                pinned_acquisition(reader, before_revalidation=await_writer_before_revalidation)
                if use_pin else reader.acquire_verified_snapshot()
            )
            reader_end = monotonic_ns()
            writer_start, writer_end, sample = pending.result(60)

        final = authority(writer).publication.payload_digest()
        if final == expected:
            raise RuntimeError("writer did not publish a new tuple")
        if use_pin:
            if reader.stale != 1 or result.tuple_digest != final:
                raise RuntimeError("did not observe a stale pin followed by a verified current tuple")
        elif result.tuple_digest != expected:
            raise RuntimeError("did not observe the production acquisition ahead of the blocked writer")
        if writer_start >= reader.scans[0][1]:
            raise RuntimeError("writer and reader scan did not overlap")
        return {
            "type": "trial", "distribution": distribution, "mode": "pinned" if use_pin else "baseline",
            "input_tuple": expected, "verified_tuple": result.tuple_digest, "final_tuple": final,
            "writer_manifest_cached_at_start": cached,
            "reader_wall_ns": reader_end - reader_start, "writer_wall_ns": writer_end - writer_start,
            "revalidation_coordination_ns": coordination_wait_ns,
            "writer_return_after_first_scan_ns": writer_end - reader.scans[0][1],
            "writer_sample": sample, "stale_attempts": reader.stale,
            "reader_scans_ns": [end - start for start, end in reader.scans],
            "writer_scans_ns": [end - start for start, end in writer.scans],
            "reader_fence_wait_hold_ns": reader.fences, "writer_fence_wait_hold_ns": writer.fences,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--reports", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--distribution", choices=("balanced", "concentrated"))
    parser.add_argument("--warm-writer-manifest", action="store_true")
    args = parser.parse_args()
    wheel_digest = _installed_wheel_digest(args.wheel)
    for distribution in ("balanced", "concentrated"):
        if args.distribution is not None and args.distribution != distribution:
            continue
        report = json.loads((args.reports / f"{distribution}-measurement.json").read_text())
        expected = report["fixture"]["partition_tuple_digest"]
        print(json.dumps({
            "type": "identity", "revision": report["revision"], "qualification_wheel_sha256": report["wheel_sha256"],
            "probe_wheel_sha256": wheel_digest, "distribution": distribution, "input_tuple": expected,
        }), flush=True)
        for use_pin in (False, True) if distribution == "balanced" else (True, False):
            result = trial(
                args.fixtures / distribution, args.work, distribution, expected, use_pin,
                warm_writer_manifest=args.warm_writer_manifest,
            )
            print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
