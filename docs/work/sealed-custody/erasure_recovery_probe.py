"""Disposable signer-loss recovery proof with a two-file managed inventory."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import stat
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from time import time_ns
from typing import Literal

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import BaseModel, ConfigDict


class ErasureDenied(RuntimeError):
    """The fixture has no authority or proof to advance deletion."""


class Receipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation: str
    outcome: Literal["erased"]
    completed_ns: int
    signature: str

    def signing_bytes(self) -> bytes:
        return b"memorii.fixture-erasure-receipt.v1\0" + self.model_dump_json(exclude={"signature"}).encode()


class ErasureState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation: str
    owner: str
    phase: Literal["confirmed", "removing_data", "signer_recorded", "signer_removal", "complete"]
    image_digest: str
    signer_digest: str
    signer_public: str
    erasure_proof: str | None = None
    receipt: Receipt | None = None

    def erasure_statement(self) -> bytes:
        return f"memorii.fixture-erasure.v1\0{self.operation}\0{self.image_digest}\0{self.signer_digest}".encode()


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_file(path: Path) -> bytes:
    with _open_regular(path) as handle:
        return handle.read()


def _open_regular(path: Path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ErasureDenied("fixture artifact must be a regular file")
        return os.fdopen(descriptor, "rb", buffering=0)
    except BaseException:
        os.close(descriptor)
        raise


def _file_digest(path: Path) -> str:
    with _open_regular(path) as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _delete_expected(path: Path, digest: str) -> None:
    if os.path.lexists(path):
        if _file_digest(path) != digest:
            raise ErasureDenied("managed file was substituted")
        path.unlink()
    _sync_directory(path.parent)


class FixtureLedger:
    def __init__(self, work: Path) -> None:
        self.db = work / "supervisor" / "ledger.sqlite3"
        self.key = Ed25519PrivateKey.from_private_bytes(_read_file(work / "supervisor" / "signer"))
        self.image = work / "installation" / "image.sqlite3"
        self.signer = work / "installation" / "signer"
        self.signer_public = work / "supervisor" / "installation-public"

    def _connect(self, *, create: bool = False) -> sqlite3.Connection:
        mode = "rwc" if create else "rw"
        connection = sqlite3.connect(self.db.as_uri() + "?mode=" + mode, uri=True)
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _require_managed_inventory(self) -> None:
        if {entry.name for entry in self.image.parent.iterdir()} - {self.image.name, self.signer.name}:
            raise ErasureDenied("unknown managed fixture artifact")

    def confirm(self, owner: str, operation: str, *, confirmed: bool) -> None:
        if not confirmed:
            raise ErasureDenied("explicit confirmation required")
        self._require_managed_inventory()
        record = ErasureState(
            operation=operation, owner=owner, phase="confirmed",
            image_digest=_file_digest(self.image), signer_digest=_file_digest(self.signer),
            signer_public=_read_file(self.signer_public).hex(),
        )
        payload = record.model_dump_json()
        with closing(self._connect(create=True)) as connection, connection:
            connection.execute("CREATE TABLE IF NOT EXISTS erasure(id INTEGER PRIMARY KEY, payload TEXT, signature BLOB)")
            connection.execute("INSERT INTO erasure VALUES (1,?,?)", (payload, self.key.sign(payload.encode())))
        _sync_directory(self.db.parent)

    def require_available(self) -> None:
        if os.path.lexists(self.db):
            raise ErasureDenied("erasure intent closes startup")

    def _current(self, owner: str, operation: str) -> tuple[str, ErasureState]:
        with closing(self._connect()) as connection:
            payload, signature = connection.execute("SELECT payload,signature FROM erasure WHERE id=1").fetchone()
        self.key.public_key().verify(signature, payload.encode())
        record = ErasureState.model_validate_json(payload)
        if (record.owner, record.operation) != (owner, operation):
            raise ErasureDenied("only the original owner and operation may resume")
        return payload, record

    def _advance(self, previous: str, record: ErasureState) -> None:
        payload = record.model_dump_json()
        with closing(self._connect()) as connection, connection:
            updated = connection.execute(
                "UPDATE erasure SET payload=?, signature=? WHERE id=1 AND payload=?",
                (payload, self.key.sign(payload.encode()), previous),
            )
            if updated.rowcount != 1:
                raise ErasureDenied("erasure ledger changed")

    def record_erasure(self, owner: str, operation: str) -> None:
        """Obtain the installation owner's proof and observe that process exit."""
        previous, record = self._current(owner, operation)
        self._require_managed_inventory()
        if record.phase == "confirmed":
            if not self.image.is_file():
                raise ErasureDenied("image absent before deletion checkpoint")
            record = record.model_copy(update={"phase": "removing_data"})
            self._advance(previous, record)
            previous = record.model_dump_json()
        if record.phase != "removing_data":
            raise ErasureDenied("data removal requires its durable checkpoint")
        if _file_digest(self.signer) != record.signer_digest:
            raise ErasureDenied("installation signer was substituted")
        _delete_expected(self.image, record.image_digest)
        proof = subprocess.run(
            [sys.executable, "-W", "error", __file__, "proof", str(self.signer), record.signer_digest],
            input=record.erasure_statement(), capture_output=True, check=True, timeout=10,
        ).stdout
        self._advance(previous, record.model_copy(update={"phase": "signer_recorded", "erasure_proof": proof.hex()}))

    def retire_worker(self, owner: str, operation: str) -> None:
        """Call only after synchronously observing the temporary owner process exit."""
        previous, record = self._current(owner, operation)
        if record.phase != "signer_recorded" or not record.erasure_proof or os.path.lexists(self.image):
            raise ErasureDenied("no proven data deletion and retired signer owner")
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(record.signer_public)).verify(
            bytes.fromhex(record.erasure_proof), record.erasure_statement(),
        )
        if _file_digest(self.signer) != record.signer_digest:
            raise ErasureDenied("signer identity changed before the unlink checkpoint")
        self._advance(previous, record.model_copy(update={"phase": "signer_removal"}))

    def finish(self, owner: str, operation: str, cut: str = "") -> Receipt:
        previous, record = self._current(owner, operation)
        if record.phase == "complete" and record.receipt is not None:
            return record.receipt
        self._require_managed_inventory()
        if record.phase != "signer_removal" or os.path.lexists(self.image):
            raise ErasureDenied("signer removal has no durable authority")
        if cut == "before-unlink":
            os._exit(70)
        _delete_expected(self.signer, record.signer_digest)
        if cut == "after-unlink":
            os._exit(70)
        if os.path.lexists(self.signer):
            raise ErasureDenied("installation signing key survives")
        unsigned = Receipt(operation=operation, outcome="erased", completed_ns=time_ns(), signature="")
        receipt = unsigned.model_copy(update={"signature": self.key.sign(unsigned.signing_bytes()).hex()})
        self._advance(previous, record.model_copy(update={"phase": "complete", "receipt": receipt}))
        if cut == "after-receipt":
            os._exit(70)
        return receipt


def main() -> None:
    if sys.argv[1] == "proof":
        path, expected = sys.argv[2:]
        signer = _read_file(Path(path))
        if hashlib.sha256(signer).hexdigest() != expected:
            raise ErasureDenied("signer identity changed before proof")
        sys.stdout.buffer.write(Ed25519PrivateKey.from_private_bytes(signer).sign(sys.stdin.buffer.read()))
        return
    action, work, owner, operation, cut = sys.argv[1:]
    ledger = FixtureLedger(Path(work))
    if action == "record" and not cut:
        ledger.record_erasure(owner, operation)
    elif action == "finish":
        print(ledger.finish(owner, operation, cut).model_dump_json())
    else:
        raise ValueError("unsupported fixture command")


if __name__ == "__main__":
    main()
