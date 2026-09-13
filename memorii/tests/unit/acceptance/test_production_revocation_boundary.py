"""Production reader boundary and acceptance revocation evidence proof."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from acceptance.ctv import encode_typed_value
from acceptance.production_revocation import (
    IndependentProductionRevocationEvidenceVerifier,
    ProductionRevocationEvidenceError,
)
from acceptance.production_revocation_bridge import SerializedProductionRevocationEvidence
from acceptance.schema_registry import (
    canonical_digest,
    decode_artifact,
    load_registry,
    lp,
    schema_for,
    signing_preimage,
    unsigned_artifact,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from memorii.core.memory_evolution.deployment_authorization import (
    InstalledProductionRevocationPublisher,
    InstalledProductionRevocationReader,
)


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")


def _time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _artifact(
    schema: str, signer: Ed25519PrivateKey, coordinate: str, **fields: object
) -> tuple[str, bytes]:
    registered = schema_for(schema)
    value = dict(fields)
    digest_field = registered["digest_field"]
    value[digest_field] = "0" * 64
    value["signing_key_coordinate"] = coordinate
    value["signature"] = "0" * 128
    value[digest_field] = canonical_digest(
        registered["digest_domain"], "registered", unsigned_artifact(value, schema)
    )
    value["signature"] = signer.sign(signing_preimage(schema, value, coordinate)).hex()
    digest = value[digest_field]
    if not isinstance(digest, str):
        raise AssertionError("registered artifact digest is not text")
    return digest, _json(value)


def _signed_unchecked_artifact(
    schema: str, signer: Ed25519PrivateKey, coordinate: str, **fields: object
) -> bytes:
    """Sign bytes without invoking the acceptance descriptor validator."""
    registered = schema_for(schema)
    value = dict(fields)
    digest_field = registered["digest_field"]
    value[digest_field] = "0" * 64
    value["signing_key_coordinate"] = coordinate
    value["signature"] = "0" * 128
    unsigned = unsigned_artifact(value, schema)
    digest = canonical_digest(registered["digest_domain"], "registered", unsigned)
    value[digest_field] = digest
    preimage = lp(registered["signature_domain"].encode("ascii")) + lp(
        encode_typed_value(
            {
                "purpose": registered["purpose"],
                "profile_binding": load_registry()["profile"],
                "signer_coordinate": coordinate,
                "body_digest": digest,
                "unsigned_content": unsigned,
            }
        )
    )
    value["signature"] = signer.sign(preimage).hex()
    return _json(value)


class _Reader:
    def __init__(self, evidence: SerializedProductionRevocationEvidence, parents: dict[str, bytes]) -> None:
        self.evidence = evidence
        self.parents = parents
        self.outage = False

    def read_for_prior_release(self, _: str) -> SerializedProductionRevocationEvidence:
        if self.outage:
            raise OSError("reader unavailable")
        return self.evidence

    def load_checkpoint(self, checkpoint_digest: str) -> bytes:
        return self.parents[checkpoint_digest]


def _evidence(checkpoint_epoch: int = 2) -> tuple[
    str, bytes, bytes, dict[str, bytes], Ed25519PrivateKey, str
]:
    key = Ed25519PrivateKey.generate()
    coordinate = "production-revocation-1"
    now = datetime(2026, 9, 13, tzinfo=UTC)
    prior_release = "a" * 64
    receipt_digest, receipt = _artifact(
        "ProductionRevocationReceipt",
        key,
        coordinate,
        schema_version=1,
        purpose="production_revocation_receipt",
        prior_approval_release_digest=prior_release,
        withdrawal_requested_at=_time(now),
        prior_production_epoch=1,
        advanced_production_epoch=2,
        completed_at=_time(now + timedelta(seconds=1)),
    )
    parent_digest, parent = _artifact(
        "ProductionEpochCheckpoint",
        key,
        coordinate,
        schema_version=1,
        purpose="production_epoch_checkpoint",
        production_authority_snapshot_digest="b" * 64,
        checkpoint_generation=1,
        predecessor_checkpoint_digest=None,
        active_production_epoch=1,
        active_authorization_digests=["c" * 64],
        revocation_receipt_digests=["d" * 64],
        observed_at=_time(now),
    )
    _, checkpoint = _artifact(
        "ProductionEpochCheckpoint",
        key,
        coordinate,
        schema_version=1,
        purpose="production_epoch_checkpoint",
        production_authority_snapshot_digest="b" * 64,
        checkpoint_generation=2,
        predecessor_checkpoint_digest=parent_digest,
        active_production_epoch=checkpoint_epoch,
        active_authorization_digests=["c" * 64],
        revocation_receipt_digests=[receipt_digest],
        observed_at=_time(now + timedelta(seconds=2)),
    )
    return prior_release, receipt, checkpoint, {parent_digest: parent}, key, coordinate


def _verifier(reader: _Reader, key: Ed25519PrivateKey, coordinate: str) -> IndependentProductionRevocationEvidenceVerifier:
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return IndependentProductionRevocationEvidenceVerifier(reader=reader, trust_keys={coordinate: public})


def test_independent_revocation_verifier_requires_current_signed_chain() -> None:
    prior, receipt, checkpoint, parents, key, coordinate = _evidence()
    reader = _Reader(SerializedProductionRevocationEvidence(receipt, checkpoint), parents)
    verifier = _verifier(reader, key, coordinate)
    verified_receipt, verified_checkpoint = verifier.verify(
        prior_approval_release_digest=prior,
        receipt=receipt,
        checkpoint=checkpoint,
        require_current_reader_bytes=True,
    )
    assert verified_receipt["prior_approval_release_digest"] == prior
    assert verified_checkpoint["checkpoint_generation"] == 2
    # Recovery re-reads the independently owned current mapping and bytes.
    verifier.verify(
        prior_approval_release_digest=prior,
        receipt=receipt,
        checkpoint=checkpoint,
        require_current_reader_bytes=True,
    )


def test_independent_revocation_verifier_allows_later_current_epoch() -> None:
    prior, receipt, checkpoint, parents, key, coordinate = _evidence(checkpoint_epoch=3)
    verifier = _verifier(_Reader(SerializedProductionRevocationEvidence(receipt, checkpoint), parents), key, coordinate)
    verifier.verify(
        prior_approval_release_digest=prior,
        receipt=receipt,
        checkpoint=checkpoint,
        require_current_reader_bytes=True,
    )


def test_independent_revocation_verifier_fails_closed_on_reader_outage_after_restart() -> None:
    prior, receipt, checkpoint, parents, key, coordinate = _evidence()
    reader = _Reader(SerializedProductionRevocationEvidence(receipt, checkpoint), parents)
    verifier = _verifier(reader, key, coordinate)
    verifier.verify(
        prior_approval_release_digest=prior,
        receipt=receipt,
        checkpoint=checkpoint,
        require_current_reader_bytes=True,
    )
    reader.outage = True
    with pytest.raises(ProductionRevocationEvidenceError, match="reader"):
        verifier.verify(
            prior_approval_release_digest=prior,
            receipt=receipt,
            checkpoint=checkpoint,
            require_current_reader_bytes=True,
        )


@pytest.mark.parametrize("mutation", ["wrong_signer", "stale", "membership", "epoch"])
def test_independent_revocation_verifier_fails_closed(mutation: str) -> None:
    prior, receipt, checkpoint, parents, key, coordinate = _evidence()
    reader = _Reader(SerializedProductionRevocationEvidence(receipt, checkpoint), parents)
    if mutation == "wrong_signer":
        verifier = IndependentProductionRevocationEvidenceVerifier(
            reader=reader, trust_keys={"other": b"x" * 32}
        )
    elif mutation == "stale":
        reader.evidence = SerializedProductionRevocationEvidence(receipt, checkpoint + b" ")
        verifier = _verifier(reader, key, coordinate)
    else:
        value = json.loads(checkpoint)
        if mutation == "membership":
            value["revocation_receipt_digests"] = ["e" * 64]
        else:
            value["active_production_epoch"] = 3
        # Mutating signed canonical bytes must fail before any weaker join could pass.
        checkpoint = _json(value)
        reader.evidence = SerializedProductionRevocationEvidence(receipt, checkpoint)
        verifier = _verifier(reader, key, coordinate)
    with pytest.raises(ProductionRevocationEvidenceError):
        verifier.verify(
            prior_approval_release_digest=prior,
            receipt=receipt,
            checkpoint=checkpoint,
            require_current_reader_bytes=True,
        )


def test_production_file_reader_returns_only_canonical_current_mapping(tmp_path: Path) -> None:
    prior, receipt, checkpoint, parents, _, _ = _evidence()
    root = tmp_path / "production"
    objects = root / "objects"
    current = root / "current"
    objects.mkdir(parents=True)
    current.mkdir()
    receipt_digest = json.loads(receipt)["receipt_digest"]
    checkpoint_digest = json.loads(checkpoint)["checkpoint_digest"]
    (objects / receipt_digest).write_bytes(receipt)
    (objects / checkpoint_digest).write_bytes(checkpoint)
    for digest, raw in parents.items():
        (objects / digest).write_bytes(raw)
    (current / f"{prior}.json").write_bytes(
        _json({"prior_approval_release_digest": prior, "receipt_digest": receipt_digest, "checkpoint_digest": checkpoint_digest})
    )
    reader = InstalledProductionRevocationReader().from_fixed_configuration({"reader_root": str(root)})
    observed = reader.read_for_prior_release(prior)
    assert observed.receipt == receipt
    assert observed.checkpoint == checkpoint
    (current / f"{prior}.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="production_revocation_current"):
        reader.read_for_prior_release(prior)


def test_production_file_reader_rejects_insecure_root_or_ancestor_before_io(tmp_path: Path) -> None:
    insecure_root = tmp_path / "insecure-root"
    insecure_root.mkdir(mode=0o700)
    os.chmod(insecure_root, 0o777)
    with pytest.raises(ValueError, match="production_revocation_reader_path"):
        InstalledProductionRevocationReader().from_fixed_configuration(
            {"reader_root": str(insecure_root)}
        )

    secure_root = tmp_path / "secure-root"
    secure_root.mkdir(mode=0o700)
    insecure_parent = secure_root / "insecure-parent"
    insecure_parent.mkdir(mode=0o700)
    os.chmod(insecure_parent, 0o775)
    with pytest.raises(ValueError, match="production_revocation_reader_path"):
        InstalledProductionRevocationReader().from_fixed_configuration(
            {"reader_root": str(insecure_parent / "leaf")}
        )
    assert not (insecure_parent / "leaf" / "current").exists()


def test_production_file_reader_requires_preprovisioned_secure_root(tmp_path: Path) -> None:
    root = tmp_path / "operator-must-provision"
    with pytest.raises(ValueError, match="production_revocation_reader_path"):
        InstalledProductionRevocationReader().from_fixed_configuration(
            {"reader_root": str(root)}
        )
    assert not root.exists()


def test_production_file_reader_exposes_no_mutation_capability(tmp_path: Path) -> None:
    root = tmp_path / "read-only-production"
    root.mkdir(mode=0o700)
    reader = InstalledProductionRevocationReader().from_fixed_configuration(
        {"reader_root": str(root)}
    )
    assert "_publish_revocation_evidence" not in vars(type(reader))
    assert not (root / "objects").exists()
    assert not (root / "current").exists()


def test_production_file_reader_lease_preserves_caller_oserror(tmp_path: Path) -> None:
    root = tmp_path / "read-only-production"
    root.mkdir(mode=0o700)
    now = datetime(2026, 9, 13, tzinfo=UTC)
    reader = InstalledProductionRevocationReader().from_fixed_configuration(
        {"reader_root": str(root)}
    )
    artifact = SimpleNamespace(
        verified_capability_baseline_approval_release_digest="a" * 64,
        expires_at=now + timedelta(minutes=1),
    )
    with (
        pytest.raises(OSError, match="caller storage failure"),
        reader.current_use(artifact=artifact, server_time=now) as current,
    ):
        assert current is True
        raise OSError("caller storage failure")


@pytest.mark.parametrize("mutation", ("signature", "unknown_key", "digest", "join"))
def test_registered_production_publisher_rejects_forged_evidence_before_write(
    tmp_path: Path, mutation: str,
) -> None:
    prior, receipt, checkpoint, _, key, coordinate = _evidence()
    root = tmp_path / "production"
    root.mkdir(mode=0o700)
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    publisher = InstalledProductionRevocationPublisher().from_fixed_configuration({
        "reader_root": str(root), "trust_keys": {coordinate: public.hex()},
    })
    if mutation == "signature":
        receipt = receipt[:-1] + (b"0" if receipt[-1:] != b"0" else b"1")
    elif mutation == "unknown_key":
        publisher = InstalledProductionRevocationPublisher().from_fixed_configuration({
            "reader_root": str(root), "trust_keys": {"unknown": public.hex()},
        })
    elif mutation == "digest":
        value = json.loads(receipt)
        value["receipt_digest"] = "0" * 64
        receipt = _json(value)
    else:
        value = json.loads(checkpoint)
        value["revocation_receipt_digests"] = ["0" * 64]
        checkpoint = _json(value)
    with pytest.raises(ValueError):
        publisher.publish_verified(
            prior_approval_release_digest=prior, receipt=receipt, checkpoint=checkpoint,
        )
    assert not (root / "objects").exists()
    assert not (root / "current").exists()


@pytest.mark.parametrize("mutation", ("integer_maximum", "string_ceiling", "array_ceiling"))
def test_registered_production_publisher_matches_frozen_schema_constraints_before_write(
    tmp_path: Path, mutation: str,
) -> None:
    prior, receipt, checkpoint, _, key, coordinate = _evidence()
    root = tmp_path / "production"
    root.mkdir(mode=0o700)
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    publisher = InstalledProductionRevocationPublisher().from_fixed_configuration({
        "reader_root": str(root), "trust_keys": {coordinate: public.hex()},
    })
    if mutation == "integer_maximum":
        value = json.loads(receipt)
        receipt = _signed_unchecked_artifact(
            "ProductionRevocationReceipt",
            key,
            coordinate,
            **{
                key_name: (2**63 if key_name == "prior_production_epoch" else item)
                for key_name, item in value.items()
                if key_name not in {"receipt_digest", "signing_key_coordinate", "signature"}
            },
        )
        invalid_schema, invalid_raw = "ProductionRevocationReceipt", receipt
    else:
        value = json.loads(checkpoint)
        if mutation == "string_ceiling":
            invalid_coordinate = "k" * 16_385
            fields = {
                key_name: item
                for key_name, item in value.items()
                if key_name not in {"checkpoint_digest", "signing_key_coordinate", "signature"}
            }
        else:
            invalid_coordinate = coordinate
            fields = {
                key_name: ([f"{index:064x}" for index in range(1_025)] if key_name == "active_authorization_digests" else item)
                for key_name, item in value.items()
                if key_name not in {"checkpoint_digest", "signing_key_coordinate", "signature"}
            }
        checkpoint = _signed_unchecked_artifact(
            "ProductionEpochCheckpoint", key, invalid_coordinate, **fields
        )
        if mutation == "string_ceiling":
            publisher = InstalledProductionRevocationPublisher().from_fixed_configuration({
                "reader_root": str(root), "trust_keys": {invalid_coordinate: public.hex()},
            })
        invalid_schema, invalid_raw = "ProductionEpochCheckpoint", checkpoint
    with pytest.raises(ValueError):
        decode_artifact(invalid_raw, invalid_schema)
    with pytest.raises(ValueError):
        publisher.publish_verified(
            prior_approval_release_digest=prior, receipt=receipt, checkpoint=checkpoint,
        )
    assert not (root / "objects").exists()
    assert not (root / "current").exists()


@pytest.mark.parametrize("zero_first_write", (False, True))
def test_registered_production_publisher_handles_short_mapping_writes_and_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, zero_first_write: bool,
) -> None:
    prior, receipt, checkpoint, parents, key, coordinate = _evidence()
    root = tmp_path / "production"
    objects = root / "objects"
    root.mkdir(mode=0o700)
    objects.mkdir(mode=0o700)
    for digest, raw in parents.items():
        (objects / digest).write_bytes(raw)
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    publisher = InstalledProductionRevocationPublisher().from_fixed_configuration({
        "reader_root": str(root), "trust_keys": {coordinate: public.hex()},
    })
    real_write = os.write
    calls = 0

    def constrained_write(descriptor: int, payload: bytes) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            if zero_first_write:
                return 0
            return real_write(descriptor, payload[:7])
        return real_write(descriptor, payload)

    monkeypatch.setattr(os, "write", constrained_write)
    if zero_first_write:
        with pytest.raises(ValueError, match="production_revocation_publish"):
            publisher.publish_verified(
                prior_approval_release_digest=prior,
                receipt=receipt,
                checkpoint=checkpoint,
            )
        assert not (root / "current" / f"{prior}.json").exists()
        monkeypatch.setattr(os, "write", real_write)
    publisher.publish_verified(
        prior_approval_release_digest=prior, receipt=receipt, checkpoint=checkpoint,
    )
    observed = InstalledProductionRevocationReader().from_fixed_configuration(
        {"reader_root": str(root)}
    ).read_for_prior_release(prior)
    assert observed.receipt == receipt
    assert observed.checkpoint == checkpoint
