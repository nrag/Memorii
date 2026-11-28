"""Disposable Linux proof of OS custody, peer identity and retained-owner handoff."""

from __future__ import annotations

import errno
import fcntl
import json
import os
import select
import shutil
import signal
import socket
import sqlite3
import struct
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from retained_vfs_probe import block_table, retained_reader

_SERVICE = 19001
_CLIENT = 19002
_LEGACY = 19003
_CONTENT = b"protected-custody-fixture"
_LOCK_CONFLICT = 73


def _caps() -> str:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("CapEff:"):
            return line.split()[1]
    raise RuntimeError("cannot inspect effective Linux capabilities")


def _peer(connection: socket.socket) -> tuple[int, int, int]:
    return struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))


def _protected_read(connection: sqlite3.Connection) -> bytes:
    result, = connection.execute("SELECT body FROM fixture WHERE id=1").fetchone()
    if result != _CONTENT:
        raise RuntimeError("retained view selected different content")
    return result


def _worker(root: Path, extension: Path, expected: str, endpoint: int, gate: int) -> int:
    # Owner lock is outside the replaceable partition directory. Only the
    # independently spawned worker holds the lock and native data handles.
    lock = os.open(root / ".owner.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return _LOCK_CONFLICT
        with os.fdopen(gate, "rb", buffering=0) as supervisor:
            if supervisor.read(1) != b"1":
                raise RuntimeError("supervisor withdrew startup")
            with (
                socket.socket(fileno=endpoint) as listener,
                retained_reader(root / "partition" / "data.sqlite3", expected, extension) as reader,
            ):
                reader.release(_protected_read)
                print(json.dumps({"pid": os.getpid(), "uid": os.geteuid(), "caps": _caps()}), flush=True)
                while True:
                    ready, _, _ = select.select([supervisor, listener], [], [])
                    if supervisor in ready:
                        return 0
                    connection, _ = listener.accept()
                    with connection:
                        connection.settimeout(3)
                        if _peer(connection)[1] != _CLIENT:
                            continue
                        if connection.recv(64) != b"read":
                            continue
                        result = reader.release(_protected_read)
                        if select.select([supervisor], [], [], 0)[0]:
                            return 0
                        connection.sendall(result)
    finally:
        os.close(lock)


def _direct(root: Path) -> None:
    image = root / "partition" / "data.sqlite3"
    for mode in ("rb", "r+b"):
        try:
            with image.open(mode):
                raise RuntimeError("legacy principal reached the enrolled image")
        except PermissionError as exc:
            if exc.errno != errno.EACCES:
                raise
    try:
        with closing(sqlite3.connect(image.as_uri() + "?mode=ro", uri=True)):
            raise RuntimeError("legacy SQLite reached the enrolled image")
    except sqlite3.OperationalError as exc:
        if exc.sqlite_errorcode != sqlite3.SQLITE_CANTOPEN:
            raise
    print(json.dumps({"uid": os.geteuid(), "caps": _caps(), "direct_read": "EACCES", "direct_write": "EACCES",
                      "sqlite_open": "SQLITE_CANTOPEN"}), flush=True)


def _client(endpoint: Path, expected: str) -> None:
    with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as connection:
        connection.settimeout(3)
        connection.connect(str(endpoint))
        supervisor = _peer(connection)[1]
        if supervisor != 0:
            raise RuntimeError("socket was not created by the trusted fixture supervisor")
        if expected == "waiting":
            connection.sendall(b"read")
            if select.select([connection], [], [], 0.2)[0]:
                raise RuntimeError("socket produced a response before the worker became ready")
            print(json.dumps({"uid": os.geteuid(), "caps": _caps(), "endpoint_uid": supervisor,
                              "result": "request_waiting_without_bytes"}), flush=True)
            if connection.recv(128) != _CONTENT:
                raise RuntimeError("the parked request did not use the acquired view")
            expected = "allowed_after_readiness"
        elif expected == "denied":
            try:
                connection.sendall(b"read")
                reply = connection.recv(128)
            except (BrokenPipeError, ConnectionResetError):
                reply = b""
            if reply:
                raise RuntimeError("an unauthorized peer received protected bytes")
        else:
            connection.sendall(b"read")
            if connection.recv(128) != _CONTENT:
                raise RuntimeError("authorized peer did not receive the retained SQLite response")
        print(json.dumps({"uid": os.geteuid(), "caps": _caps(), "endpoint_uid": supervisor,
                          "result": expected}), flush=True)


def _legacy(path: Path) -> None:
    with path.open("r+b", buffering=0) as old:
        offset = old.read().index(_CONTENT)
        print(json.dumps({"uid": os.geteuid(), "caps": _caps(), "inode": os.fstat(old.fileno()).st_ino}), flush=True)
        if sys.stdin.buffer.read(1) != b"1":
            raise RuntimeError("legacy fixture write was not requested")
        old.seek(offset)
        old.write(b"!")


def _argv(*args: str | Path | int) -> list[str]:
    return [sys.executable, "-B", "-W", "error", __file__, *(str(arg) for arg in args)]


def _launch(uid: int, *args: str | Path | int, pass_fds: tuple[int, ...] = ()) -> subprocess.Popen:
    return subprocess.Popen(
        _argv(*args), user=uid, group=uid, extra_groups=[], pass_fds=pass_fds,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    )


def _await_line(child: subprocess.Popen) -> dict[str, object]:
    if not select.select([child.stdout], [], [], 10)[0]:
        raise TimeoutError("child did not report readiness")
    line = child.stdout.readline()
    if not line:
        raise RuntimeError(f"child terminated before readiness, status={child.poll()}")
    evidence = json.loads(line)
    if int(evidence["caps"], 16):
        raise RuntimeError("fixture child retained effective capabilities")
    return evidence


def _check(uid: int, *args: str | Path) -> dict[str, object]:
    output = subprocess.run(
        _argv(*args), user=uid, group=uid, extra_groups=[], check=True, capture_output=True, timeout=10,
    )
    evidence = json.loads(output.stdout)
    if evidence["uid"] != uid or int(evidence["caps"], 16):
        raise RuntimeError("fixture client ran outside its expected identity")
    return evidence


def _terminate(child: subprocess.Popen) -> None:
    try:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=10)
    finally:
        child.stdin.close()
        child.stdout.close()


def _start_worker(root: Path, extension: Path, expected: str, listener: socket.socket) -> tuple[subprocess.Popen, int]:
    gate, release = os.pipe()
    try:
        child = _launch(
            _SERVICE, "worker", root, extension, expected, listener.fileno(), gate,
            pass_fds=(listener.fileno(), gate),
        )
    except BaseException:
        os.close(release)
        raise
    finally:
        os.close(gate)
    return child, release


def _supervise(extension: Path) -> None:
    if sys.platform != "linux" or os.geteuid() != 0:
        raise RuntimeError("run only as the supervisor of a disposable root-owned Linux container")
    with TemporaryDirectory(prefix="memorii-owner-") as directory:
        fixture = Path(directory)
        fixture.chmod(0o711)
        prior = fixture / "legacy.sqlite3"
        with closing(sqlite3.connect(prior)) as old, old:
            old.execute("CREATE TABLE fixture(id INTEGER PRIMARY KEY, body BLOB NOT NULL)")
            old.execute("INSERT INTO fixture VALUES(1, ?)", (_CONTENT,))
        prior.chmod(0o600)
        os.chown(prior, _LEGACY, _LEGACY)
        legacy = _launch(_LEGACY, "legacy", prior)
        try:
            prior_owner = _await_line(legacy)
            root = fixture / "enrolled"
            partition = root / "partition"
            partition.mkdir(mode=0o700, parents=True)
            image = partition / "data.sqlite3"
            shutil.copyfile(prior, image)
            new_inode = image.stat().st_ino
            if new_inode == prior_owner["inode"]:
                raise RuntimeError("enrollment reused the old writable inode")
            with image.open("rb") as source:
                _, _, expected = block_table(source.fileno())
            image.chmod(0o600)
            root.chmod(0o700)
            for owned in (image, partition, root):
                os.chown(owned, _SERVICE, _SERVICE)
            legacy.stdin.write(b"1")
            legacy.stdin.flush()
            if legacy.wait(timeout=10) != 0 or _CONTENT in prior.read_bytes():
                raise RuntimeError("legacy process did not mutate its pre-existing writable descriptor")
            direct = _check(_LEGACY, "direct", root)
            authorized_direct = _check(_CLIENT, "direct", root)

            endpoint = fixture / "owner.sock"
            with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as listener:
                listener.bind(str(endpoint))
                endpoint.chmod(0o666)
                listener.listen(4)
                owner, boot = _start_worker(root, extension, expected, listener)
                try:
                    waiting = _launch(_CLIENT, "client", endpoint, "waiting")
                    try:
                        before_ready = _await_line(waiting)
                        if before_ready["uid"] != _CLIENT or before_ready["result"] != "request_waiting_without_bytes":
                            raise RuntimeError("startup was not tested by the intended peer with a pending read")
                        os.write(boot, b"1")
                        first = _await_line(owner)
                        parked = _await_line(waiting)
                        if waiting.wait(timeout=5) != 0 or parked["result"] != "allowed_after_readiness":
                            raise RuntimeError("ready-owner handoff did not release the waiting request")
                    finally:
                        _terminate(waiting)
                    allowed = _check(_CLIENT, "client", endpoint, "allowed")
                    blocked = _check(_LEGACY, "client", endpoint, "denied")
                    # An independent process under the same service UID reaches
                    # the lock and must stop before opening the retained image.
                    contender, rejected_gate = _start_worker(root, extension, expected, listener)
                    try:
                        conflict = contender.wait(timeout=5)
                        if conflict != _LOCK_CONFLICT or owner.poll() is not None:
                            raise RuntimeError("a successor acquired custody while the worker retained SQLite")
                    finally:
                        os.close(rejected_gate)
                        _terminate(contender)
                    owner.kill()
                    death = owner.wait(timeout=10)
                    if death != -signal.SIGKILL:
                        raise RuntimeError("predecessor did not exit at the injected kill cut")
                finally:
                    os.close(boot)
                    _terminate(owner)
                successor, boot = _start_worker(root, extension, expected, listener)
                try:
                    os.write(boot, b"1")
                    second = _await_line(successor)
                    after_restart = _check(_CLIENT, "client", endpoint, "allowed")
                    os.close(boot)
                    boot = -1
                    supervisor_loss_exit = successor.wait(timeout=5)
                    if supervisor_loss_exit != 0:
                        raise RuntimeError("worker did not close its view on supervisor-channel loss")
                finally:
                    if boot >= 0:
                        os.close(boot)
                    _terminate(successor)
            if first["uid"] != _SERVICE or second["uid"] != _SERVICE or first["pid"] == second["pid"]:
                raise RuntimeError("the supervisor did not hand off between two service processes")
            print(json.dumps({
                "runtime": {"python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version, "platform": sys.platform},
                "old_writer": prior_owner, "enrolled_inode": new_inode, "legacy_direct": direct,
                "authorized_client_direct": authorized_direct, "before_ready": before_ready,
                "parked_request": parked, "authorized_client": allowed, "unauthorized_client": blocked,
                "first_owner": first, "contender_exit": conflict, "first_owner_exit": death,
                "successor": second, "after_restart": after_restart, "supervisor_loss_exit": supervisor_loss_exit,
            }, sort_keys=True))
        finally:
            _terminate(legacy)


def main() -> int:
    action, *args = sys.argv[1:]
    if action == "supervise":
        _supervise(Path(args[0]))
    elif action == "worker":
        root, extension, expected, endpoint, gate = args
        return _worker(Path(root), Path(extension), expected, int(endpoint), int(gate))
    elif action == "legacy":
        _legacy(Path(args[0]))
    elif action == "direct":
        _direct(Path(args[0]))
    elif action == "client":
        _client(Path(args[0]), args[1])
    else:
        raise ValueError("unknown fixture action")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
