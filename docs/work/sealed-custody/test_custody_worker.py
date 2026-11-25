"""Exercise the private retained worker through real local socket handoffs."""

from __future__ import annotations

import fcntl
import socket
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest
from checkpoint_capacity import change_mode
from measure_sealed_startup import prepare_fixture
from memorii.core.harness_state.grant_registry import GrantRegistryError
from memorii.core.memory_plane.file_lock import locked_file
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.storage_administration.operator_backup import _backup_lifetime_guard
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.domain.enums import CommitStatus, MemoryDomain
from retained_vfs_probe import ReleaseDenied
from retained_worker import DrainBusy, RetainedWorker
from test_retained_vfs import _COLD, _HOT, _read_blob, _root
from test_retained_vfs import image as image  # noqa: PLC0414
from tests.support.reference_capacity import TaskAllocation
from tests.support.reference_capacity_fixture import _prepare


def _received(client: socket.socket) -> bytes:
    client.settimeout(5)
    return b"".join(iter(lambda: client.recv(65536), b""))


def _park(entered: Event, resume: Event) -> None:
    entered.set()
    assert resume.wait(5)


def test_completed_response_precedes_grant_revocation(
    tmp_path: Path, image: tuple[Path, str, int], extension: Path,
) -> None:
    path, root, _ = image
    worker = RetainedWorker(tmp_path, path, root, extension)
    try:
        sender, client = socket.socketpair()
        with client:
            assert worker.serve(sender, "grant", 1, lambda db: _read_blob(db, 1)) == len(_HOT)
            assert _received(client) == _HOT
        worker.revoke("grant")
        sender, client = socket.socketpair()
        with client:
            with pytest.raises(GrantRegistryError, match="stale_grant"):
                worker.serve(sender, "grant", 1, lambda db: _read_blob(db, 1))
            assert _received(client) == b""
    finally:
        worker.drain(timeout=5)


@pytest.mark.parametrize("denial", ["revocation", "integrity"])
def test_buffered_response_denied_after_competing_event(
    tmp_path: Path, image: tuple[Path, str, int], extension: Path, denial: str,
) -> None:
    path, root, position = image
    worker = RetainedWorker(tmp_path, path, root, extension)
    entered, resume = Event(), Event()
    sender, client = socket.socketpair()
    try:
        with client, ThreadPoolExecutor(1) as requests:
            pending = requests.submit(
                worker.serve, sender, "grant", 1, lambda db: _read_blob(db, 1),
                before_send=lambda: _park(entered, resume),
            )
            try:
                assert entered.wait(5)
                if denial == "revocation":
                    worker.revoke("grant")
                else:
                    with path.open("r+b", buffering=0) as external:
                        external.seek(position)
                        external.write(b"!")
                    detector, peer = socket.socketpair()
                    with peer:
                        with pytest.raises(ReleaseDenied, match="latched closed"):
                            worker.serve(detector, "other", 1, lambda db: _read_blob(db, 2, tail=True))
                        assert _received(peer) == b""
            finally:
                resume.set()
            expected = GrantRegistryError if denial == "revocation" else ReleaseDenied
            with pytest.raises(expected):
                pending.result(timeout=5)
            assert _received(client) == b""
    finally:
        worker.drain(timeout=5)


def test_slow_socket_releases_fence_and_revocation_stops_unsent_bytes(
    tmp_path: Path, image: tuple[Path, str, int], extension: Path,
) -> None:
    path, root, _ = image
    worker = RetainedWorker(tmp_path, path, root, extension)
    entered, resume = Event(), Event()
    sender, client = socket.socketpair()
    sender.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
    try:
        with client, ThreadPoolExecutor(1) as requests:
            pending = requests.submit(
                worker.serve, sender, "grant", 1, lambda db: _read_blob(db, 2),
                on_backpressure=lambda: _park(entered, resume),
            )
            try:
                assert entered.wait(5)
                worker.revoke("grant")
            finally:
                resume.set()
            received = _received(client)
            with pytest.raises(GrantRegistryError, match="stale_grant"):
                pending.result(timeout=5)
            assert 0 < len(received) < len(_COLD)
            assert _COLD.startswith(received)
    finally:
        worker.drain(timeout=5)


def test_drained_worker_hands_off_to_ordinary_verified_v8_writer(
    tmp_path: Path, extension: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "installation"
    _prepare(root, "balanced", (TaskAllocation("balanced", 0, 3, 9, 0, 0, 2),), raw_payloads=True)
    with StorageAdministrationService(root) as owner:
        _, prior = owner._active_partition_selection()
        assert prior is not None
    path, expected = prepare_fixture(root, prior.payload_digest())
    worker = RetainedWorker(root, path, _root(path), extension)
    entered, resume = Event(), Event()
    sender, client = socket.socketpair()
    try:
        with client, ThreadPoolExecutor(1) as requests:
            pending = requests.submit(
                worker.serve, sender, "grant", 1,
                lambda db: db.execute("SELECT tuple_digest FROM partition_publication").fetchone()[0].encode(),
                before_send=lambda: _park(entered, resume),
            )
            try:
                assert entered.wait(5)
                with pytest.raises(DrainBusy):
                    worker.drain(timeout=0)
                with locked_file(root / ".publication.lock", exclusive=True):
                    pass
                lifetime = root / "control" / ".backup-lifetime.lock"
                with lifetime.open("rb") as contender, pytest.raises(BlockingIOError):
                    fcntl.flock(contender.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                resume.set()
            with pytest.raises(ReleaseDenied, match="admissions are closed"):
                pending.result(timeout=5)
            assert _received(client) == b""
    finally:
        worker.drain(timeout=5)

    exact_calls = []
    original = StorageAdministrationService._matches_materialization

    def observe_exact(self, connection, finalized, **kwargs):
        exact_calls.append(finalized.payload_digest())
        return original(self, connection, finalized, **kwargs)

    monkeypatch.setattr(StorageAdministrationService, "_matches_materialization", observe_exact)
    with StorageAdministrationService(root) as owner, _backup_lifetime_guard(owner, exclusive=True):
        assert owner.acquire_verified_snapshot().tuple_digest == expected
        assert exact_calls == [expected]
        change_mode(owner, "active")
        owner.publish_memory_plane_batch((CanonicalMemoryRecord(
            memory_id="after-handoff", domain=MemoryDomain.TRANSCRIPT, text="new data",
            source_kind="fixture", status=CommitStatus.COMMITTED,
        ),))
        published = owner.acquire_verified_snapshot()
        assert published.tuple_digest != expected
    with StorageAdministrationService(root) as fresh:
        assert fresh.acquire_verified_snapshot() == published
        assert fresh.memory_plane_store().get_record("after-handoff") is not None
