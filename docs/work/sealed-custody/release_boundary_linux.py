"""End-to-end socket release races for the private isolated Linux owner."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import select
import socket
import sqlite3
import subprocess
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

from owner_boundary_probe import (
    _CLIENT,
    _SERVICE,
    _await_line,
    _caps,
    _peer,
    _terminate,
)
from retained_vfs_probe import ReleaseDenied, block_table

_PRINCIPAL = "fixture-reader"
_GRANT = "fixture-grant"
_DENIALS = {
    "invalid_signature": "current signed publication failed validation",
    "different_publication": "signed publication changed after acquisition",
    "rotate": "credential no longer authorized",
    "rotate_under_pressure": "credential no longer authorized",
    "revoke_under_pressure": "stale_grant",
    "supervisor_loss": "sealed worker admissions are closed",
    "supervisor_loss_under_pressure": "sealed worker admissions are closed",
}


def _emit(event: str, **values: object) -> None:
    print(json.dumps({"event": event, "caps": _caps(), **values}), flush=True)


def _read_body(connection: sqlite3.Connection, rowid: int) -> bytes:
    with connection.blobopen("memory_payloads", "body", rowid, readonly=True) as body:
        return body.read()


def _worker(
    root: Path, extension: Path, image_root: str, task: str, rowid: int,
    listener_fd: int, supervisor_fd: int, resume_fd: int, case: str,
) -> None:

    from memorii.core.harness_state.grant_registry import GrantRegistryError
    from memorii.core.harness_state.service import RuntimeReadGrant
    from memorii.core.memory_plane.file_lock import locked_file
    from release_authority_probe import ReleaseAuthority
    from retained_worker import RetainedWorker

    grant = RuntimeReadGrant(
        grant_id=_GRANT, principal=_PRINCIPAL, allowed_task_ids=(task,), epoch=1,
        expires_at=datetime.now(UTC) + timedelta(minutes=2),
    )
    pressure = case.endswith("under_pressure")
    with (
        locked_file(root / ".owner.lock", exclusive=True),
        socket.socket(fileno=listener_fd) as listener,
        os.fdopen(supervisor_fd, "rb", buffering=0) as supervisor,
        os.fdopen(resume_fd, "rb", buffering=0) as resume,
    ):
        authority = ReleaseAuthority(root, _PRINCIPAL)
        worker = RetainedWorker(root, authority.image, image_root, extension, verify_view=authority.verify_view)
        stop = Event()

        def monitor() -> None:
            while not stop.is_set():
                if select.select([supervisor], [], [], 0.05)[0] and not supervisor.read(1):
                    worker.stop_admissions()
                    _emit("supervisor_loss_observed")
                    return

        def park(sent: int = 0) -> None:
            _emit("parked", stage="backpressure" if pressure else "before_first_byte", sent=sent)
            if resume.read(1) != b"1":
                raise RuntimeError("controller did not release the fixture barrier")

        def read(connection: sqlite3.Connection) -> bytes:
            body = _read_body(connection, rowid)
            return len(body).to_bytes(8, "big") + body

        with ThreadPoolExecutor(1) as watcher:
            observing = watcher.submit(monitor)
            try:
                _emit("ready", uid=os.geteuid(), pid=os.getpid(), publication=authority.coordinate[1].payload_digest())
                listener.settimeout(10)
                for request in range(2 if case.startswith("rotate") else 1):
                    connection, _ = listener.accept()
                    with connection:
                        if _peer(connection)[1] != _CLIENT:
                            raise RuntimeError("unexpected fixture peer UID")
                        connection.settimeout(5)
                        with connection.makefile("rb") as request_stream:
                            wire = request_stream.readline(256)
                        if not wire.endswith(b"\n"):
                            raise RuntimeError("request must carry one bounded credential")
                        secret = wire[:-1].decode("ascii")
                        before = request == 0 and case != "valid"
                        if before and pressure:
                            connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
                        check_authority = authority.guard(secret, grant, task)

                        def guard(check: Callable[[], None] = check_authority) -> None:
                            check()
                            if select.select([supervisor], [], [], 0)[0]:
                                raise ReleaseDenied("supervisor channel closed")

                        try:
                            outcome = worker.serve(
                                connection, grant.grant_id, grant.epoch, read,
                                release_guard=guard,
                                before_send=park if before and not pressure else None,
                                on_backpressure=park if before and pressure else None,
                            )
                        except (ReleaseDenied, GrantRegistryError) as exc:
                            _emit("response_denied", request=request, reason=str(exc))
                        else:
                            _emit("response_sent", request=request, bytes=outcome)
            finally:
                stop.set()
                observing.result(timeout=5)
                worker.drain(timeout=5)
                _emit("retained_view_closed")


def _client(endpoint: Path, slow: bool) -> None:
    secret = sys.stdin.buffer.readline(256)
    if not secret.endswith(b"\n"):
        raise RuntimeError("missing fixture credential")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(10)
        connection.connect(str(endpoint))
        if _peer(connection)[1] != 0:
            raise RuntimeError("untrusted listener")
        connection.sendall(secret)
        if slow and sys.stdin.buffer.read(1) != b"1":
            raise RuntimeError("controller did not enable receiving")
        received = b"".join(iter(lambda: connection.recv(65536), b""))
    complete = len(received) >= 8 and int.from_bytes(received[:8], "big") == len(received) - 8
    _emit("received", uid=os.geteuid(), bytes=len(received), digest=hashlib.sha256(received).hexdigest(), complete=complete)


def _spawn(uid: int, *args: object, pass_fds: tuple[int, ...] = ()) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-B", "-W", "error", __file__, *(str(arg) for arg in args)],
        user=uid, group=uid, extra_groups=[], pass_fds=pass_fds,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    )


def _expect(child: subprocess.Popen, event: str) -> dict[str, object]:
    record = _await_line(child)
    if record["event"] != event:
        raise RuntimeError(f"expected {event}, observed {record}")
    return record


def _publication_change(root: Path, case: str) -> None:

    from memorii.core.persistence.key_owner import RUNTIME_PUBLICATION_SIGNATURE_PURPOSE
    from memorii.core.storage_administration.service import StorageAdministrationService

    with StorageAdministrationService(root) as owner, owner._publication_fence():
        _, publication = owner._active_partition_selection()
        if publication is None:
            raise RuntimeError("fixture is missing its named publication")
        if case == "invalid_signature":
            changed = publication.model_copy(update={"signature": "0" * 128})
            if changed.payload_digest() != publication.payload_digest():
                raise RuntimeError("signature-only test changed the payload digest")
        else:
            changed = owner._sign_state(publication.model_copy(update={"manifest_digest": "a" * 64}))
            if changed.payload_digest() == publication.payload_digest() or not owner._signing.verify(
                owner._signer_key_id, RUNTIME_PUBLICATION_SIGNATURE_PURPOSE, changed.payload_digest(), changed.signature,
            ):
                raise RuntimeError("fixture failed to create a distinct authentic control tuple")
        # Intentionally update control only. The pinned image cannot follow it.
        owner._control.write_publication_state(
            changed.repository_id, changed, owner._journal_entry(
                operation="publication_finalized", before_digest=publication.payload_digest(),
                after_digest=changed.payload_digest(),
            ),
        )


def _fixture(root: Path) -> tuple[str, int, str, str, bytes]:

    from measure_sealed_startup import prepare_fixture
    from memorii.core.harness_state.credentials import SidecarCredentialStore
    from memorii.core.memory_plane.models import CanonicalMemoryRecord
    from memorii.core.storage_administration.service import StorageAdministrationService
    from memorii.domain.enums import CommitStatus, MemoryDomain
    from tests.support.reference_capacity import TaskAllocation
    from tests.support.reference_capacity_fixture import _prepare

    allocation = TaskAllocation("balanced", 0, 3, 9, 0, 0, 2)
    _prepare(root, "balanced", (allocation,), raw_payloads=True)
    with StorageAdministrationService(root) as owner:
        owner.publish_memory_plane_batch((CanonicalMemoryRecord(
            memory_id="release-race-body", domain=MemoryDomain.TRANSCRIPT,
            text="x" * 180_000, source_kind="fixture", task_id=allocation.task_id, status=CommitStatus.COMMITTED,
        ),))
        _, publication = owner._active_partition_selection()
        if publication is None:
            raise RuntimeError("fixture did not publish its named tuple")
    path, expected = prepare_fixture(root, publication.payload_digest())
    with StorageAdministrationService(root) as owner:
        if owner.acquire_verified_snapshot().tuple_digest != expected:
            raise RuntimeError("fixture did not verify the exact retained publication")
    with closing(sqlite3.connect(path)) as database:
        rowid, = database.execute(
            "SELECT p.rowid FROM memory_current_records AS c JOIN memory_payloads AS p USING(payload_digest)"
            " WHERE c.memory_id=? AND c.task_id=?",
            ("release-race-body", allocation.task_id),
        ).fetchone()
        body = _read_body(database, rowid)
        if not 65_536 <= len(body) < 512 * 1024 - 8:
            raise RuntimeError("reply must hit socket backpressure while staying within the worker buffer limit")
    with path.open("rb") as source:
        _, _, image_root = block_table(source.fileno())
    _, secret = SidecarCredentialStore(root / "control" / "credentials").issue(_PRINCIPAL)
    root.chmod(0o700)
    for entry in (root, *root.rglob("*")):
        os.chown(entry, _SERVICE, _SERVICE)
    return allocation.task_id, rowid, image_root, secret, len(body).to_bytes(8, "big") + body


def _spawn_client(endpoint: Path, secret: str, slow: bool) -> subprocess.Popen:
    child = _spawn(_CLIENT, "client", endpoint, int(slow))
    child.stdin.write(secret.encode("ascii") + b"\n")
    child.stdin.flush()
    return child


def _checked_client(child: subprocess.Popen, expected: bytes, minimum: int, maximum: int) -> dict[str, object]:
    result = _expect(child, "received")
    size = result["bytes"]
    if (
        child.wait(timeout=5) != 0 or result["uid"] != _CLIENT or not minimum <= size <= maximum
        or result["digest"] != hashlib.sha256(expected[:size]).hexdigest()
        or result["complete"] != (size == len(expected))
    ):
        raise RuntimeError("wire output differs from the authorized portion of the fixture")
    return result


def _mutate(root: Path, case: str) -> None:
    if case in {"invalid_signature", "different_publication"}:
        _publication_change(root, case)
    elif case.startswith("rotate"):

        from release_authority_probe import rotate_fixture_credential

        previous = sys.stdin.buffer.readline(256)
        if not previous.endswith(b"\n"):
            raise RuntimeError("missing credential expected by the fixture controller")
        print(rotate_fixture_credential(root, previous[:-1].decode("ascii")), flush=True)
    elif case == "revoke_under_pressure":

        from memorii.core.harness_state.grant_registry import GrantEpochRegistry
        from memorii.core.memory_plane.file_lock import locked_file

        with locked_file(root / ".publication.lock", exclusive=True):
            GrantEpochRegistry(root / "control" / "grants").revoke(_GRANT, reason="fixture")
    else:
        raise RuntimeError("unknown authority mutation")


def _change_authority(root: Path, case: str, secret: str) -> str | None:
    # The owner UID performs mutations. The controller uses a private
    # subprocess pipe for bearer secrets and publishes no credential contents.
    result = subprocess.run(
        [sys.executable, "-B", "-W", "error", __file__, "mutate", str(root), case],
        user=_SERVICE, group=_SERVICE, extra_groups=[], input=secret + "\n", text=True,
        stdout=subprocess.PIPE, check=True, timeout=10,
    )
    return result.stdout.strip() if case.startswith("rotate") else None


def _probe_lock(root: Path) -> int:
    with (root / ".owner.lock").open("rb") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 73
    return 0


def _owner_lock_status(root: Path) -> int:
    child = _spawn(_SERVICE, "probe-lock", root)
    try:
        return child.wait(timeout=5)
    finally:
        _terminate(child)


def _run_case(work: Path, extension: Path, case: str) -> None:
    work.mkdir(mode=0o711)
    root = work / "installation"
    task, rowid, image_root, secret, expected = _fixture(root)
    endpoint = work / "owner.sock"
    pressure = case.endswith("under_pressure")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(endpoint))
        endpoint.chmod(0o666)
        listener.listen(4)
        live_read, live_write = os.pipe()
        resume_read, resume_write = os.pipe()
        # Kill the process that holds the only live write end to produce EOF.
        holder = _spawn(0, "hold-liveness", live_write, pass_fds=(live_write,))
        os.close(live_write)
        owner = _spawn(
            _SERVICE, "worker", root, extension, image_root, task, rowid,
            listener.fileno(), live_read, resume_read, case,
            pass_fds=(listener.fileno(), live_read, resume_read),
        )
        os.close(live_read)
        os.close(resume_read)
        try:
            ready = _expect(owner, "ready")
            if ready["uid"] != _SERVICE:
                raise RuntimeError("wrong service UID")
            client = _spawn_client(endpoint, secret, pressure)
            try:
                replacement = None
                parked_offset = None
                if case != "valid":
                    parked = _expect(owner, "parked")
                    if parked["stage"] != ("backpressure" if pressure else "before_first_byte"):
                        raise RuntimeError("test missed the intended release boundary")
                    parked_offset = parked["sent"]
                    if (pressure and not 0 < parked_offset < len(expected)) or (not pressure and parked_offset != 0):
                        raise RuntimeError("test missed the required socket offset")
                    if case.startswith("supervisor_loss"):
                        if _owner_lock_status(root) != 73:
                            raise RuntimeError("a contender could acquire custody during the paused release")
                        holder.kill()
                        if holder.wait(timeout=5) != -9:
                            raise RuntimeError("liveness supervisor did not die at the test cut")
                        _expect(owner, "supervisor_loss_observed")
                    else:
                        replacement = _change_authority(root, case, secret)
                    os.write(resume_write, b"1")
                    if pressure:
                        client.stdin.write(b"1")
                        client.stdin.flush()
                if case == "valid":
                    outcome = _expect(owner, "response_sent")
                    actual = _checked_client(client, expected, len(expected), len(expected))
                else:
                    outcome = _expect(owner, "response_denied")
                    actual = _checked_client(client, expected, parked_offset, parked_offset)
                    if not outcome["reason"].startswith(_DENIALS[case]):
                        raise RuntimeError("release failed at the wrong authority gate")
            finally:
                _terminate(client)
            fresh_bytes = None
            if replacement is not None:
                fresh = _spawn_client(endpoint, replacement, False)
                try:
                    _expect(owner, "response_sent")
                    fresh_bytes = _checked_client(fresh, expected, len(expected), len(expected))["bytes"]
                finally:
                    _terminate(fresh)
            _expect(owner, "retained_view_closed")
            if owner.wait(timeout=5) != 0:
                raise RuntimeError("owner did not drain")
            successor_lock = _owner_lock_status(root) if case.startswith("supervisor_loss") else None
            if successor_lock not in (0, None):
                raise RuntimeError("a contender could not acquire the lock after the retained owner drained")
            print(json.dumps({
                "case": case, "client_bytes": actual["bytes"], "complete": actual["complete"],
                "outcome": outcome["event"], "reason": outcome.get("reason"), "expected_bytes": len(expected),
                "replacement_bytes": fresh_bytes, "owner_drained": True,
                "successor_lock": successor_lock, "parked_bytes": parked_offset,
            }, sort_keys=True), flush=True)
        finally:
            os.close(resume_write)
            _terminate(owner)
            _terminate(holder)


def main() -> int:
    action, *args = sys.argv[1:]
    if action == "supervise":
        if sys.platform != "linux" or os.geteuid() != 0:
            raise RuntimeError("run only in the disposable root-owned Linux fixture")
        extension = Path(args[0])
        with TemporaryDirectory(prefix="memorii-release-") as temporary:
            root = Path(temporary)
            root.chmod(0o711)
            for case in args[1:] or ("valid", *_DENIALS):
                if case not in ("valid", *_DENIALS):
                    raise RuntimeError("unknown release case")
                _run_case(root / case, extension, case)
    elif action == "worker":
        root, extension, image_root, task, rowid, listener, live, resume, case = args
        _worker(Path(root), Path(extension), image_root, task, int(rowid), int(listener), int(live), int(resume), case)
    elif action == "client":
        _client(Path(args[0]), args[1] == "1")
    elif action == "mutate":
        _mutate(Path(args[0]), args[1])
    elif action == "probe-lock":
        return _probe_lock(Path(args[0]))
    elif action == "hold-liveness":
        with os.fdopen(int(args[0]), "wb"):
            sys.stdin.buffer.read(1)
    else:
        raise RuntimeError("unknown fixture action")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
