"""Recover the isolated Linux socket owner after loss of its actual supervisor."""

from __future__ import annotations

import fcntl
import json
import os
import select
import signal
import socket
import sqlite3
import subprocess
import sys
from contextlib import ExitStack, closing
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from owner_boundary_probe import _SERVICE, _terminate
from release_boundary_linux import (
    _checked_client,
    _expect,
    _fixture,
    _owner_lock_status,
    _spawn_client,
)


@dataclass(frozen=True)
class Predecessor:
    enrollment: str
    publication: str
    worker_pid: int

    def statement(self, phase: str) -> bytes:
        return b"memorii.fixture-supervisor-exit.v1\0" + json.dumps(
            [self.enrollment, self.publication, self.worker_pid, phase], separators=(",", ":"),
        ).encode("ascii")


def _ledger(path: Path, mode: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path.as_uri() + f"?mode={mode}", uri=True)
    connection.execute("PRAGMA synchronous=FULL").close()
    return connection


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _record_pending(path: Path, signer: Ed25519PrivateKey, predecessor: Predecessor) -> None:
    payload = predecessor.statement("pending")
    with closing(_ledger(path, "rwc")) as ledger, ledger:
        ledger.execute("CREATE TABLE handoff (id INTEGER PRIMARY KEY CHECK(id=1), payload BLOB, signature BLOB)")
        ledger.execute("INSERT INTO handoff VALUES (1, ?, ?)", (payload, signer.sign(payload)))
    _sync_directory(path.parent)


def _exited(pidfd: int, timeout_ms: int) -> bool:
    poller = select.poll()
    poller.register(pidfd, select.POLLIN)
    return any(events & select.POLLIN for _, events in poller.poll(timeout_ms))


def _record_exit(path: Path, signer: Ed25519PrivateKey, predecessor: Predecessor, pidfd: int) -> None:
    if not _exited(pidfd, 5000):
        raise RuntimeError("kernel did not report predecessor exit")
    pending = predecessor.statement("pending")
    exited = predecessor.statement("exited")
    with closing(_ledger(path, "rw")) as ledger, ledger:
        updated = ledger.execute(
            "UPDATE handoff SET payload=?, signature=? WHERE id=1 AND payload=? AND signature=?",
            (exited, signer.sign(exited), pending, signer.sign(pending)),
        ).rowcount
        if updated != 1:
            raise RuntimeError("authenticated pending handoff is missing")


def _exit_proven(path: Path, verifier: Ed25519PublicKey, predecessor: Predecessor) -> bool:
    try:
        with closing(_ledger(path, "ro")) as ledger:
            record = ledger.execute("SELECT payload, signature FROM handoff WHERE id=1").fetchone()
        if record is None or record[0] != predecessor.statement("exited"):
            return False
        verifier.verify(record[1], record[0])
    except (sqlite3.Error, InvalidSignature, TypeError):
        return False
    return True


def _supervise(
    work: Path, extension: Path, image_root: str, task: str, rowid: int, resume_fd: int,
    case: str, recovery: list[str],
) -> int:
    root = work / "installation"
    endpoint = work / "owner.sock"
    witness = work / "witness"
    with ExitStack() as descriptors:
        guard = descriptors.enter_context((witness / "supervisor.lock").open("ab"))
        fcntl.flock(guard.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        publication = ""
        if recovery:
            public, enrollment, publication, pid = recovery
            predecessor = Predecessor(enrollment, publication, int(pid))
            if not _exit_proven(witness / "handoff.sqlite3", Ed25519PublicKey.from_public_bytes(
                bytes.fromhex(public),
            ), predecessor):
                return 74
        else:
            try:
                (witness / "enrolled").touch(mode=0o600, exist_ok=False)
            except FileExistsError:
                return 76
            _sync_directory(witness)
        lock_fd = os.open(root / ".owner.lock", os.O_RDONLY | os.O_NOFOLLOW)
        ownership = descriptors.enter_context(os.fdopen(lock_fd, "rb"))
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 75
        if recovery:
            # This one-handoff fixture cannot authorize a third worker from the first exit.
            try:
                (witness / "handoff-used").touch(mode=0o600, exist_ok=False)
            except FileExistsError:
                return 77
            _sync_directory(witness)
            endpoint.unlink()
        listener = descriptors.enter_context(socket.socket(socket.AF_UNIX, socket.SOCK_STREAM))
        listener.bind(str(endpoint))
        endpoint.chmod(0o666)
        listener.listen(4)
        live_read, live_write = os.pipe()
        descriptors.callback(os.close, live_write)
        try:
            worker = subprocess.Popen(
                [sys.executable, "-B", "-W", "error", str(Path(__file__).with_name("release_boundary_linux.py")),
                 "worker", str(root), str(extension), image_root, task, str(rowid), str(listener.fileno()),
                 str(live_read), str(resume_fd), case, publication, str(lock_fd)],
                user=_SERVICE, group=_SERVICE, extra_groups=[],
                pass_fds=(listener.fileno(), live_read, resume_fd, lock_fd), stdin=subprocess.DEVNULL,
            )
        finally:
            os.close(live_read)
        # The worker retains the same locked open file description until its view closes.
        ownership.close()
        try:
            return worker.wait(timeout=45)
        finally:
            if worker.poll() is None:
                worker.kill()
                worker.wait(timeout=5)


def _start(*args: object, resume_fd: int) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-B", "-W", "error", __file__, "supervise", str(resume_fd), *(str(arg) for arg in args)],
        pass_fds=(resume_fd,), stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0, start_new_session=True,
    )


def _stop_supervisor(child: subprocess.Popen) -> None:
    if child.poll() is None:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    _terminate(child)


def _stop_orphan(pidfd: int) -> None:
    if not _exited(pidfd, 0):
        try:
            signal.pidfd_send_signal(pidfd, signal.SIGKILL)
        except ProcessLookupError:
            pass
        if not _exited(pidfd, 5000):
            raise RuntimeError("fixture worker failed to exit during cleanup")


def _denied_start(status: int, endpoint: Path, *args: object, resume_fd: int) -> None:
    endpoint_inode = endpoint.stat().st_ino
    child = _start(*args, resume_fd=resume_fd)
    try:
        if child.wait(timeout=5) != status or child.stdout.read(1) or endpoint.stat().st_ino != endpoint_inode:
            raise RuntimeError("uncertain handoff reached listener replacement or worker readiness")
    finally:
        _stop_supervisor(child)


def _run(work: Path, extension: Path, pressure: bool) -> None:
    work.mkdir(mode=0o711)
    witness = work / "witness"
    witness.mkdir(mode=0o700)
    ledger = witness / "handoff.sqlite3"
    root = work / "installation"
    endpoint = work / "owner.sock"
    task, rowid, image_root, secret, expected = _fixture(root)
    lock = root / ".owner.lock"
    lock.touch(mode=0o600, exist_ok=False)
    os.chown(lock, _SERVICE, _SERVICE)
    case = "supervisor_loss_under_pressure" if pressure else "supervisor_loss"
    arguments = (work, extension, image_root, task, rowid)
    signer = Ed25519PrivateKey.generate()
    public = signer.public_key().public_bytes_raw().hex()

    with ExitStack() as stack:
        resume_read, resume_write = os.pipe()
        stack.callback(os.close, resume_read)
        stack.callback(os.close, resume_write)
        original = _start(*arguments, case, resume_fd=resume_read)
        stack.callback(_stop_supervisor, original)
        ready = _expect(original, "ready")
        if ready["uid"] != _SERVICE:
            raise RuntimeError("wrong worker identity")
        predecessor = Predecessor(uuid4().hex, ready["publication"], ready["pid"])
        successor_args = (*arguments, "valid", public, predecessor.enrollment, predecessor.publication, predecessor.worker_pid)
        pidfd = os.pidfd_open(predecessor.worker_pid)
        stack.callback(os.close, pidfd)
        stack.callback(_stop_orphan, pidfd)

        client = _spawn_client(endpoint, secret, pressure)
        stack.callback(_terminate, client)
        parked = _expect(original, "parked")
        sent = parked["sent"]
        if pressure and not 0 < sent < len(expected) or not pressure and sent != 0:
            raise RuntimeError("did not reach the intended socket boundary")
        if pressure:
            _record_pending(ledger, signer, predecessor)
        original.kill()
        if original.wait(timeout=5) != -signal.SIGKILL:
            raise RuntimeError("actual supervisor did not die")
        _expect(original, "supervisor_loss_observed")
        if _exited(pidfd, 0) or _owner_lock_status(root) != 73:
            raise RuntimeError("parked predecessor lost its retained custody")
        if not pressure:
            _denied_start(74, endpoint, *successor_args, resume_fd=resume_read)
            _record_pending(ledger, signer, predecessor)
        _denied_start(76, endpoint, *arguments, "valid", resume_fd=resume_read)
        _denied_start(74, endpoint, *successor_args, resume_fd=resume_read)

        os.write(resume_write, b"1")
        if pressure:
            client.stdin.write(b"1")
            client.stdin.flush()
        denied = _expect(original, "response_denied")
        if denied["reason"] != "sealed worker admissions are closed":
            raise RuntimeError("interrupted read failed at the wrong boundary")
        _expect(original, "retained_view_closed")
        interrupted = _checked_client(client, expected, sent, sent)
        _record_exit(ledger, signer, predecessor, pidfd)
        exited = predecessor.statement("exited")
        with closing(_ledger(ledger, "rw")) as connection, connection:
            connection.execute("UPDATE handoff SET signature=zeroblob(64)")
        _denied_start(74, endpoint, *successor_args, resume_fd=resume_read)
        with closing(_ledger(ledger, "rw")) as connection, connection:
            connection.execute("UPDATE handoff SET signature=?", (signer.sign(exited),))

        _denied_start(
            74, endpoint, *arguments, "valid", public, uuid4().hex, predecessor.publication, predecessor.worker_pid,
            resume_fd=resume_read,
        )
        wrong_public = Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex()
        _denied_start(
            74, endpoint, *arguments, "valid", wrong_public, predecessor.enrollment, predecessor.publication,
            predecessor.worker_pid, resume_fd=resume_read,
        )
        with lock.open("rb") as anchored:
            fcntl.flock(anchored.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            _denied_start(75, endpoint, *successor_args, resume_fd=resume_read)

        successor = _start(*successor_args, resume_fd=resume_read)
        stack.callback(_stop_supervisor, successor)
        recovered = _expect(successor, "ready")
        if (
            recovered["publication"] != predecessor.publication or recovered["uid"] != _SERVICE
            or recovered["pid"] == predecessor.worker_pid or successor.pid == original.pid
        ):
            raise RuntimeError("successor selected a different owner or signed publication")
        fresh = _spawn_client(endpoint, secret, False)
        stack.callback(_terminate, fresh)
        _expect(successor, "response_sent")
        complete = _checked_client(fresh, expected, len(expected), len(expected))
        _expect(successor, "retained_view_closed")
        if successor.wait(timeout=5) != 0:
            raise RuntimeError("recovered supervisor did not reap its worker")
        _denied_start(77, endpoint, *successor_args, resume_fd=resume_read)
        print(json.dumps({
            "cut": parked["stage"], "parked_bytes": sent, "interrupted_bytes": interrupted["bytes"],
            "successor_bytes": complete["bytes"], "signed_publication_reopened": True,
            "supervisor_signal": "SIGKILL", "predecessor_exit_proof": "linux_pidfd",
            "original_supervisor_pid": original.pid, "original_worker_pid": predecessor.worker_pid,
            "successor_supervisor_pid": successor.pid, "successor_worker_pid": recovered["pid"],
            "pending_written_before_kill": pressure, "missing_ledger_denied": not pressure,
            "denied": [
                "bootstrap_reuse", "pending_live_predecessor", "invalid_signature",
                "wrong_enrollment", "wrong_witness_key", "held_owner_lock", "reused_handoff",
            ],
        }, sort_keys=True), flush=True)


def main() -> int:
    if sys.platform != "linux" or os.geteuid() != 0:
        raise RuntimeError("run only in the disposable root-owned Linux fixture")
    action, *args = sys.argv[1:]
    if action == "run":
        extension, = args
        with TemporaryDirectory(prefix="memorii-supervisor-") as temporary:
            root = Path(temporary)
            root.chmod(0o711)
            _run(root / "first", Path(extension), False)
            _run(root / "pressure", Path(extension), True)
        return 0
    if action == "supervise":
        resume, work, extension, image_root, task, rowid, case, *recovery = args
        return _supervise(Path(work), Path(extension), image_root, task, int(rowid), int(resume), case, recovery)
    raise RuntimeError("unknown supervisor fixture action")


if __name__ == "__main__":
    raise SystemExit(main())
