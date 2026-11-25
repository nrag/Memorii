"""Kill disposable erasure processes around the irreversible signer boundary."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from erasure_recovery_probe import ErasureDenied, FixtureLedger, Receipt

_PROBE = Path(__file__).with_name("erasure_recovery_probe.py")
_OWNER = "fixture-owner"
_OPERATION = "confirmed-erasure"


@pytest.fixture
def erasure_fixture(tmp_path: Path) -> Path:
    for namespace in ("installation", "supervisor"):
        directory = tmp_path / namespace
        directory.mkdir(mode=0o700)
        signer = directory / "signer"
        signer.touch(mode=0o600)
        key = Ed25519PrivateKey.generate()
        signer.write_bytes(key.private_bytes_raw())
        if namespace == "installation":
            public = key.public_key().public_bytes_raw()
    (tmp_path / "supervisor" / "installation-public").write_bytes(public)
    with closing(sqlite3.connect(tmp_path / "installation" / "image.sqlite3")) as connection, connection:
        connection.execute("CREATE TABLE fixture (value TEXT)")
        connection.execute("INSERT INTO fixture VALUES ('synthetic')")
    return tmp_path


def _run(root: Path, action: str, *, cut: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-W", "error", str(_PROBE), action, str(root), _OWNER, _OPERATION, cut],
        check=False, capture_output=True, text=True, timeout=10,
    )


@pytest.mark.parametrize("cut", ["before-unlink", "after-unlink", "after-receipt"])
def test_restart_never_reopens_storage_and_replays_same_receipt(erasure_fixture: Path, cut: str) -> None:
    root = erasure_fixture
    ledger = FixtureLedger(root)
    ledger.require_available()
    ledger.confirm(_OWNER, _OPERATION, confirmed=True)
    signed = _run(root, "record")
    assert signed.returncode == 0, signed.stderr
    ledger.retire_worker(_OWNER, _OPERATION)

    interrupted = _run(root, "finish", cut=cut)
    assert interrupted.returncode == 70, interrupted.stderr
    assert (root / "installation" / "signer").exists() == (cut == "before-unlink")
    assert not (root / "installation" / "image.sqlite3").exists()
    with pytest.raises(ErasureDenied, match="closes startup"):
        FixtureLedger(root).require_available()
    with pytest.raises(ErasureDenied, match="original owner"):
        FixtureLedger(root).finish("other", _OPERATION)
    _, before_retry = FixtureLedger(root)._current(_OWNER, _OPERATION)
    assert (before_retry.receipt is not None) == (cut == "after-receipt")
    resumed = _run(root, "finish")
    assert resumed.returncode == 0, resumed.stderr
    receipt = Receipt.model_validate_json(resumed.stdout)
    assert receipt.operation == _OPERATION and receipt.outcome == "erased"
    if cut == "after-receipt":
        assert receipt == before_retry.receipt
    ledger.key.public_key().verify(bytes.fromhex(receipt.signature), receipt.signing_bytes())
    assert not (root / "installation" / "signer").exists()
    repeated = _run(root, "finish")
    assert repeated.returncode == 0, repeated.stderr
    assert repeated.stdout == resumed.stdout


def test_unconfirmed_or_early_key_loss_never_produces_completion(erasure_fixture: Path) -> None:
    root = erasure_fixture
    ledger = FixtureLedger(root)
    with pytest.raises(ErasureDenied, match="confirmation"):
        ledger.confirm(_OWNER, _OPERATION, confirmed=False)
    ledger.require_available()
    ledger.confirm(_OWNER, _OPERATION, confirmed=True)
    (root / "installation" / "signer").unlink()
    with pytest.raises(ErasureDenied, match="no durable authority"):
        FixtureLedger(root).finish(_OWNER, _OPERATION)
    assert (root / "installation" / "image.sqlite3").exists()
    with pytest.raises(ErasureDenied, match="closes startup"):
        ledger.require_available()


def test_unknown_managed_artifact_stays_undeleted(erasure_fixture: Path) -> None:
    ledger = FixtureLedger(erasure_fixture)
    ledger.confirm(_OWNER, _OPERATION, confirmed=True)
    unknown = erasure_fixture / "installation" / "untracked"
    unknown.write_bytes(b"synthetic")
    with pytest.raises(ErasureDenied, match="unknown managed"):
        ledger.record_erasure(_OWNER, _OPERATION)
    assert unknown.is_file() and ledger.image.is_file() and ledger.signer.is_file()
